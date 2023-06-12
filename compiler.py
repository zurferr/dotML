import random
import re
import string
from string import Template
from typing import Dict, List, Optional

variable_pattern = re.compile(r"\$\{([a-zA-Z0-9_.]+)}")


def substitute_variables(template: str, variables: Dict, recursive=True) -> str:
    # check if template contains variables
    if re.search(variable_pattern, template) is None:
        return template
    else:
        t = Template(template)
        # Substitute the keys with their corresponding values
        compiled_string = t.safe_substitute(variables)
        if recursive and re.search(variable_pattern, compiled_string) is not None:  # do it recursively
            compiled_string = substitute_variables(compiled_string, variables)
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
                variant_values = variant[variant_name].split(', ')
                for variant_value in variant_values:
                    variant_field = {
                        'name': cube_field['name'] + '_' + str(variant_value),
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
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    table_alias = table_name.split('.')[-1] + '_' + random_part
    return table_alias


def get_simple_variables(table_alias: str, cube_fields: Dict) -> Dict:
    field_variables = {cf: cube_fields[cf].get('sql') for cf in cube_fields}  # e.g ${revenue} - ${cost}
    # identifier_variables e.g. ${orders.total}, first replace to ${orders__total} should resolve to sql
    identifier_variables = {f"{table_alias}__{cf}": cube_fields[cf].get('sql') for cf in cube_fields}
    variables = {**{'table': table_alias}, **field_variables, **identifier_variables}
    return variables


def simple_query(cube: Dict, fields: List[str], filters: List[str], sorts: List[str], limit: Optional[int]) -> str:
    """a simple query does not require joins"""

    cube_fields = {f['name']: {**f, 'dim': True} for f in cube['dimensions']}
    cube_fields = {**cube_fields, **{f['name']: {**f, 'dim': False} for f in cube['metrics']}}
    cube_fields = {**cube_fields, **{f['name']: {**f, 'dim': False, 'window': True} for f in cube['window_metrics']}}

    # add fields variant fields
    cube_fields = expand_variants(cube_fields)

    table_alias = get_table_alias(cube.get('name'))

    variables = get_simple_variables(table_alias, cube_fields)

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
               limit: Optional[int]) -> str:
    """multi cube query require joins that handle fan out problem"""
    query = ""
    # check if cubes are connected with a join, otherwise throw an error
    for join in joins:
        for cube in cubes:
            if cube['name'] == join['left'] or cube['name'] == join['right']:
                cube['join'] = join

    # check if all cubes have a join
    for cube in cubes:
        if cube.get('join') is None:
            raise ValueError(f"Cube {cube.get('name')} has no join defined")

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
    # 1.1 get list of queried dimension fields per cube
    for cube in cubes:
        queried_dimensions = []
        for query_field in fields:
            cube_name, field_name = query_field.split('.')
            if cube_name == cube.get('name') and field_name in cube['dimensions']:
                queried_dimensions.append(field_name)
        cube['queried_dimensions'] = queried_dimensions

    # 1.2 get primary key and alias of each cube
    for cube in cubes:
        cube['pk'] = [f for f in cube['dimensions'] if f.get('primary_key', False)]
        if len(cube['pk']) == 0:
            raise ValueError(f"Cube {cube.get('name')} has no primary key defined.")
        cube['alias'] = get_table_alias(cube.get('name'))

    # 1.3 build dimensional ctes
    for cube in cubes:
        primary_key_cols = ', '.join(f"{pkp.get('sql')} as pk{i}" for i, pkp in enumerate(cube['pk']))
        join_expr = ...  # todo evaluate what are foreign queried dimensions and then join them

        foreign_dimension_cols = ', '.join([f"{cube['alias']}.{d}" for d in cube['queried_dimensions']])
        group_expr = ', '.join([f"{i + 1}" for i, pkp in enumerate(cube['pk'] + cube['queried_dimensions'])])
        cte_dimension = f"""{cube['alias']}_dimension as (
select  {primary_key_cols},
        {foreign_dimension_cols}
from {cube['table']} as {cube['alias']}
group by {group_expr}
)"""

    # 1.3 create join expression for each cube

    select_expr_dim = ', '.join([f"{f.get('sql')} as {f.get('name')}" for f in cube['dimensions']])

    # 2. join the helper cte with a cte for each cubes metrics
    # 3. join all cte's together

    return query


def generate_sql_query(cubes_config: Dict, query: Dict) -> str:
    # 1. validate query

    # read query
    fields = query['fields']
    filters = query['filters']
    sorts = query['sorts']
    limit = query['limit']

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
                    variant_values = variant[variant_name].split(', ')
                    for variant_value in variant_values:
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
        return join_query(cubes, joins, fields, filters, sorts, limit)
