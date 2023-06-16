import random
import re
import string
from string import Template
from typing import Dict, List, Optional

variable_pattern = re.compile(r"\$\{([a-zA-Z0-9_.]+)}")


def substitute_variables(template: str, variables: Dict, recursive=True, i=0) -> str:
    # check if template contains variables
    if re.search(variable_pattern, template) is None:
        return template
    else:
        t = Template(template)
        # Substitute the keys with their corresponding values
        compiled_string = t.safe_substitute(variables)
        if recursive and re.search(variable_pattern, compiled_string) is not None:  # do it recursively
            i = i + 1
            if i > 10:
                raise Exception(
                    f'Recursive substitution of variables failed. Please check your variables: {compiled_string}')
            compiled_string = substitute_variables(compiled_string, variables, i=i)
    return compiled_string


def expand_variants(cube_fields: Dict) -> Dict:
    additional_fields = {}
    fields_to_remove = []

    # resolve variants, go through all fields and add variants to cube_fields
    for cf_key in cube_fields:
        cube_field = cube_fields[cf_key]
        if cube_field.get('variants') is not None:
            for variant in cube_field['variants']:
                # variant is a dict with one key and a list of values
                # extract the key as name and the values as list
                variant_name = list(variant.keys())[0]
                variant_values = variant[variant_name]
                for variant_value in variant_values:
                    # if variant_value is a dict, extract they key as name and the value as sql
                    if isinstance(variant_value, dict):
                        key_name = list(variant_value.keys())[0]
                        variant_value = variant_value[key_name]
                    else:
                        key_name = variant_value

                    variant_field = {
                        'name': cube_field['name'] + '_' + str(key_name),
                        'sql': substitute_variables(cube_field['sql'], {variant_name: str(variant_value)},
                                                    recursive=False),
                        'dim': cube_field['dim']
                    }
                    additional_fields[variant_field['name']] = variant_field
            # remove original field
            fields_to_remove.append(cf_key)

    # remove fields that have variants
    for field_to_remove in fields_to_remove:
        del cube_fields[field_to_remove]

    # add fields variant fields
    cube_fields = {**cube_fields, **additional_fields}
    return cube_fields


def get_table_alias(table_name: str) -> str:
    # get last part of the table name and add random string to it
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    table_alias = table_name.split('.')[-1] + '_' + random_part
    return table_alias


def get_cube_fields(cube: Dict) -> Dict:
    cube_fields = {f['name']: {**f, 'dim': True} for f in cube.get('dimensions', [])}
    cube_fields = {**cube_fields, **{f['name']: {**f, 'dim': False} for f in cube.get('metrics', [])}}
    cube_fields = {**cube_fields,
                   **{f['name']: {**f, 'dim': False, 'window': True} for f in cube.get('window_metrics', [])}}
    return cube_fields


def get_simple_variables(table: str, table_alias: str, cube_fields: Dict) -> Dict:
    field_variables = {cf: cube_fields[cf].get('sql') for cf in cube_fields}  # e.g ${revenue} - ${cost}
    # identifier_variables e.g. ${orders.total}, first replace to ${orders__total} should resolve to sql
    identifier_variables = {f"{table}__{cf}": cube_fields[cf].get('sql') for cf in cube_fields}
    variables = {**{'table': table_alias}, **field_variables, **identifier_variables}
    return variables


def simple_query(cube: Dict, fields: List[str], filters: List[str], sorts: List[str], limit: Optional[int]) -> str:
    """a simple query does not require joins"""

    cube_fields = get_cube_fields(cube)

    # add fields variant fields
    cube_fields = expand_variants(cube_fields)

    table_alias = get_table_alias(cube.get('name'))

    variables = get_simple_variables(cube.get('name'), table_alias, cube_fields)

    select_fields = []
    window_fields = []

    for query_field in fields:
        field_name = query_field.split('.')[1]
        if field_name in cube_fields:
            cube_field = cube_fields[field_name]
            if cube_field.get('window', False):
                # resolve window function  // just use alias name; so replace ${revenue} with revenue
                cube_field['sql'] = cube_field['sql'].replace('${', '').replace('}', '')
                window_fields.append(cube_field)
            else:
                # resolve table placeholder e.g. ${table}.total
                # resolve nested fields, e.g. sql: ${revenue} - ${cost}
                cube_field['sql'] = substitute_variables(cube_field['sql'], variables)
                select_fields.append(cube_field)

    select_expr = ', '.join([f"{sf.get('sql')} as {sf.get('name')}" for sf in select_fields])

    from_expr = f"{cube.get('table')} as {table_alias}"

    # add filters and where clause
    where_expr = None
    if len(filters) > 0:
        where_expr = ' and '.join([f"({substitute_variables(f.replace('.', '__'), variables)})" for f in filters])

    # get the positions of the dim fields in the select_fields
    group_expr = None
    dim_positions = [i for i, sf in enumerate(select_fields) if sf.get('dim')]
    if len(dim_positions) > 0:
        group_expr = ', '.join([str(i + 1) for i in dim_positions])

    order_expr = None
    if len(sorts) > 0:  # todo add support for "desc" flag
        sort_names = [s.split('.')[1] for s in sorts]
        sort_positions = [i for i, sf in enumerate(select_fields) if sf.get('name') in sort_names]
        order_expr = ', '.join([str(i + 1) for i in sort_positions])

    # Generate sql clause
    query = f"""select {select_expr}
from {from_expr}"""

    if where_expr is not None:
        query += f"""\nwhere {where_expr}"""
    if group_expr is not None:
        query += f"""\ngroup by {group_expr}"""
    if order_expr is not None:
        query += f"""\norder by {order_expr}"""

    if len(window_fields) > 0:
        window_expr = ', '.join([f"{wf.get('sql')} as {wf.get('name')}" for wf in window_fields])
        new_query = f"""with {table_alias}_base as (
{query}
)
select *, {window_expr}
from {table_alias}_base"""
        query = new_query

    query += f"""\nlimit {limit or 5000}"""

    return query


def join_query(cubes: List[Dict], joins: List[Dict], fields: List[str], filters: List[str], sorts: List[str],
               limit: Optional[int], all_query_fields: List[str]) -> str:
    """multi cube query require joins that handle fan out problem"""
    query = ""
    # check if cubes are connected with a join, otherwise throw an error
    for join in joins:
        for cube in cubes:
            if cube['name'] == join['left'] or cube['name'] == join['right']:
                # append join to cube if not already there
                if cube.get('join') is None:
                    cube['join'] = [join]
                else:
                    cube['join'].append(join)

    # prepare all cubes
    all_queried_dimensions = {}

    for cube in cubes:
        # check if all cubes have a join
        if cube.get('join') is None:
            raise ValueError(f"Cube {cube.get('name')} has no join defined")
        # also calculate all cube_fields
        cube_fields = get_cube_fields(cube)

        # add fields variant fields
        cube_fields = expand_variants(cube_fields)

        cube['cube_fields'] = cube_fields
        cube['alias'] = get_table_alias(cube.get('name'))
        cube['cube_vars'] = get_simple_variables(table=cube.get('name'),
                                                 cube_fields=cube.get('cube_fields'),
                                                 table_alias=cube.get('alias'))

        # get primary key of each cube
        cube['pk'] = [f for f in cube['dimensions'] if f.get('primary_key', False)]
        if len(cube['pk']) == 0:
            raise ValueError(f"Cube {cube.get('name')} has no primary key defined.")

        # get list of queried dimensions in cube
        queried_dimensions = {}
        for query_field in all_query_fields:
            cube_name, field_name = query_field.split('.')
            if cube_name == cube.get('name') and field_name in cube['cube_fields'] and cube['cube_fields'][
                field_name].get('dim'):
                cube_field = cube['cube_fields'][field_name]
                cube_field['cube'] = cube
                cube_field['sql'] = substitute_variables(cube_field['sql'], cube.get('cube_vars'))
                queried_dimensions[field_name] = cube_field
                all_queried_dimensions[field_name] = cube_field
        cube['queried_dimensions'] = queried_dimensions

    # 1. for each cube aggregate a helper cte with all required dimensions (based on primary key)
    # example query:
    # with order_dimension as (
    #         select
    #         orders.id as pk,
    #         order_items.product_category as product_category
    #         left join order_items
    #         on orders.id = order_items.order_id
    #         group by 1, 2
    # )
    join_vars = {cube.get('name'): cube.get('alias') for cube in cubes}

    ctes_dim = []
    for cube in cubes:
        primary_key_cols = [f"{substitute_variables(pkp.get('sql'), cube.get('cube_vars'))} as pk{i}" for i, pkp in
                            enumerate(cube['pk'])]

        needed_join_partners = {}
        foreign_dimension_cols = []
        cube['exposing_dimension_col_names'] = []
        for qdim in all_queried_dimensions:
            # foreign dimension is a dimension that is not part of this cube
            if qdim not in cube['cube_fields']:
                qdim_dict = all_queried_dimensions.get(qdim)
                foreign_dimension_cols.append(
                    f"{qdim_dict.get('sql')} as {qdim_dict.get('name')}")
                needed_join_partners[qdim_dict.get('cube').get('name')] = qdim_dict.get('cube')
                cube['exposing_dimension_col_names'].append(f"{cube.get('alias')}_dimension.{qdim_dict.get('name')}")

        # evaluate what are foreign queried dimensions and then join them
        from_expr = f"from {cube['table']} as {cube['alias']} "
        if len(needed_join_partners) > 0:
            for needed_cube_name in needed_join_partners:
                needed_cube = needed_join_partners[needed_cube_name]
                for join in needed_cube.get('join'):
                    # only join direct partners and only needed cubes
                    left_is_cube = join.get('left') == cube['name']
                    right_is_cube = join.get('right') == cube['name']
                    other_cube = join.get('left') if right_is_cube else join.get('right')
                    other_cube_is_needed = other_cube in needed_join_partners
                    if other_cube_is_needed and (left_is_cube or right_is_cube):
                        join_type = join.get('type')
                        if right_is_cube:
                            join_type = join.get('type')  # reverse direction
                            join_type = 'left' if join_type == 'right' else join_type
                            join_type = 'right' if join_type == 'left' else join_type

                        on_sql = substitute_variables(join.get('on_sql'), join_vars, recursive=False)
                        from_expr += f""" {join_type} join {needed_cube.get('table')} as {needed_cube.get('alias')}
                        on {on_sql}"""

        group_expr = ', '.join([f"{i + 1}" for i, _ in enumerate(primary_key_cols + foreign_dimension_cols)])
        select_expr = ',\n'.join(primary_key_cols + foreign_dimension_cols)

        cte_dimension = f"""{cube['alias']}_dimension as (
select  {select_expr}
{from_expr}
group by {group_expr}
)"""
        ctes_dim.append(cte_dimension)
    print(ctes_dim)

    # 2. join the helper cte with a cte for each cubes metrics
    # example query:-- join foreign dimensions to cube, and calculate the cube alone
    # order_metrics as (
    #     select
    #         order_dimension.product_category as product_category,
    #         orders.country as country,
    #         sum(orders.total) as revenue
    #     from orders
    #     join order_dimension
    #     on orders.id = order_dimension.pk
    #     group by 1, 2
    # ),

    ctes_metrics = []
    for cube in cubes:
        # get all metrics that are queried
        queried_fields = {}
        for query_field in all_query_fields:
            cube_name, field_name = query_field.split('.')
            if cube_name == cube.get('name') and field_name in cube['cube_fields']:
                cube_field = cube['cube_fields'][field_name]
                cube_field['cube'] = cube
                cube_field['sql'] = substitute_variables(cube_field['sql'], cube.get('cube_vars'))
                queried_fields[field_name] = cube_field

        # create select and group by expressions
        cube_expressions = [f"{substitute_variables(m.get('sql'), cube.get('cube_vars'))} as {m.get('name')}" for m in
                            queried_fields.values() if not m.get('window')]  # todo add window functions
        select_expr = ',\n'.join(cube['exposing_dimension_col_names'] + cube_expressions)
        cube['exposing_metrics_col_names'] = [m.get('name') for m in queried_fields.values() if not m.get('window')]

        # join metrics with dimension cte name
        # on primary key fields
        from_expr = f"""from {cube['table']} as {cube['alias']} 
        join {cube['alias']}_dimension as {cube['alias']}_dimension 
        on {cube['alias']}.id = {cube['alias']}_dimension.pk0"""  # todo right now only 1 primary key is supported

        # get the position of the dimension fields in the select expression
        dim_positions = [i + len(cube['exposing_dimension_col_names']) for i, sf in
                         enumerate(queried_fields.values()) if sf.get('dim')]
        exposing_positions = [i for i, _ in enumerate(cube['exposing_dimension_col_names'])]
        group_expr = ', '.join(f"{p + 1}" for p in (exposing_positions + dim_positions))

        cte_metrics = f"""{cube['alias']}_metrics as (
select  {select_expr}
{from_expr}
group by {group_expr}
)"""
        ctes_metrics.append(cte_metrics)
    print(ctes_metrics)

    # 3. join all cte's together
    # example query:
    # select -- join on the dimensions of the query
    #     a.product_category,
    #     a.country,
    #     a.revenue,
    #     b.quantity
    # from order_metrics a
    # join order_items_metrics b
    # on a.booking_date = a.booking_date and b.country = b.country

    select_expr = ''
    # join column names are queried dimensions
    on_join_part_template = ' and '.join(
        [f"${{left}}.{dname} = ${{right}}.{dname}" for dname in all_queried_dimensions])
    from_expr = 'from '  # + ' join '.join([f"{cube['alias']}_metrics as {cube['alias']}_metrics" for cube in cubes])
    select_expr_parts = []
    for cube in cubes:
        select_expr_parts.extend([f"{cube.get('alias')}_metrics.{f}" for f in cube['exposing_metrics_col_names']])
        for f in cube['exposing_metrics_col_names']:  # only select queried fields
            orginal_field_name = f"{cube.get('name')}.{f}"
            if orginal_field_name in fields:
                cube['exposing_dimension_col_names'].append(f)

        cube['from_expr_part'] = f"{cube['alias']}_metrics as {cube['alias']}_metrics"

    select_expr = ', '.join(select_expr_parts)
    for i, cube in enumerate(cubes):
        if i == 0:  # first cube is handled differently
            from_expr += cube['from_expr_part']
        else:
            # todo all joins are done on the first cube todo overthink this
            from_expr += f"""\njoin {cube['from_expr_part']} 
    on {substitute_variables(on_join_part_template, {
                'left': cubes[0].get('alias') + '_metrics',
                'right': cube.get('alias') + '_metrics'
            })}"""

    # 4. add filters & sorts
    cube_name_alias_map = {cube.get('name'): cube.get('alias') + '_metrics' for cube in cubes}

    where_expr = ''
    if filters:
        all_cube_vars = {}
        for cube in cubes:
            cube_vars = cube.get('cube_vars')
            # substitute all cube values with its variables first
            new_cube_vars = {}
            for k, v in cube_vars.items():
                new_cube_vars[k] = substitute_variables(v, cube.get('cube_vars'))

            all_cube_vars.update(new_cube_vars)

        where_expr = 'where '
        where_expr += ' and '.join([f"({substitute_variables(f.replace('.', '__'), all_cube_vars)})" for f in filters])

        for cube in cubes:
            cube_alias = cube.get('alias')
            cube_alias_extension = cube_alias.split('.')[0] + '_metrics'
            where_expr = where_expr.replace(cube_alias, cube_alias_extension)

    order_expr = ''
    if sorts:
        sort_exprs = []
        for sort in sorts:
            cube_name, field_name = sort.split('.')
            cube_alias = cube_name_alias_map.get(cube_name)
            sort_exprs.append(f"{cube_alias}.{field_name}")

        order_expr = 'order by ' + ', '.join(sort_exprs)

    limit_expr = ''
    if limit:
        limit_expr = f"limit {limit}"

    query = f"""with {', '.join(ctes_dim + ctes_metrics)}
select {select_expr} 
{from_expr}
{where_expr}
{order_expr}
{limit_expr}"""

    return query


def generate_sql_query(cubes_config: Dict, query: Dict) -> str:
    # 1. validate query

    # read query
    fields = query['fields']
    filters = query.get('filters', [])
    sorts = query.get('sorts', [])
    limit = query.get('limit', 5000)

    # read cubes
    cubes = cubes_config.get('cubes', {})
    joins = cubes_config.get('joins', [])

    # create a list of all dimensions and metrics names
    # we need to merge all cubes dimensions and metrics first, then extract the names as cubename + . + fieldname
    all_fields = []
    for cube in cubes:
        for cube_field in (cube.get('dimensions', []) + cube.get('metrics', []) + cube.get('window_metrics', [])):
            if cube_field.get('variants') is None:
                all_fields.append(cube['name'] + '.' + cube_field['name'])
            else:
                for variant in cube_field['variants']:
                    variant_name = list(variant.keys())[0]
                    variant_values = variant[variant_name]
                    for variant_value in variant_values:
                        # if variant value is a dict, only take the first key
                        if isinstance(variant_value, dict):
                            variant_value = list(variant_value.keys())[0]
                        all_fields.append(cube['name'] + '.' + cube_field['name'] + '_' + str(variant_value))

    # Validate fields
    needed_cubes = []

    # to extract filter fields, we need to extract everything between ${ something.something }
    # there can be multiple filters, so we need to extract all of them, we can use regex for this
    filter_fields = []
    for fil in filters:
        filter_fields.extend(re.findall(variable_pattern, fil))

    sort_fields = [sf.split(' ')[0] for sf in sorts]

    all_query_fields = fields + filter_fields + sort_fields  # only take the first part of the sort field
    for field in all_query_fields:
        if field not in all_fields:
            raise ValueError(f"Field '{field}' does not exist in the cubes.")
        # split the field by . and get the first element to get the cube name
        cube_name = field.split('.')[0]
        if cube_name not in needed_cubes:
            needed_cubes.append(cube_name)

    if len(needed_cubes) == 0:
        raise ValueError(f"No cubes needed to generate the query. This is a bug.")
    elif len(needed_cubes) == 1:
        cube = [cube for cube in cubes if cube.get('name') == needed_cubes[0]][0]
        return simple_query(cube, fields, filters, sorts, limit)
    else:
        cubes = [cube for cube in cubes if cube.get('name') in needed_cubes]
        return join_query(cubes, joins, fields, filters, sorts, limit, all_query_fields)
