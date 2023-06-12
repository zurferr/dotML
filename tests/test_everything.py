import unittest

from compiler import generate_sql_query
from cube import load_cube_configs


class MyTestCase(unittest.TestCase):
    def test_yaml_loader(self):
        cube_configs = load_cube_configs(dir_path="../cubes")
        self.assertEqual(len(cube_configs), 1)
        self.assertEqual(cube_configs[0]['cubes'][0]['name'], 'orders')

    def test_simple_query(self):
        query = {
            "fields": ["orders.id", "orders.booking_date_week", "orders.country_id", "orders.revenue", "orders.average_order_value_rolling"],
            "filters": ["${orders.country_id} = 'COMPLETE'"],
            "sorts": ["orders.booking_date_week"],
            "limit": 10
        }

        cube_configs = load_cube_configs(dir_path="../cubes")
        sql = generate_sql_query(cube_configs[0], query)
        print(sql)


if __name__ == '__main__':
    unittest.main()
