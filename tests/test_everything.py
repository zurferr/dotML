import random
import sqlite3
import unittest
from datetime import datetime, timedelta
from typing import Dict, List

from dotml.compiler import generate_sql_query
from dotml.cube import load_cube_configs


class MyTestCase(unittest.TestCase):

    @staticmethod
    def create_dummy_data():

        conn = sqlite3.connect('shopy.db')
        c = conn.cursor()

        # skip function if tables already exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='my_orders'")
        if c.fetchone() is not None:
            return

        # Create tables
        c.execute('''
             CREATE TABLE my_orders (
                 id INTEGER PRIMARY KEY,
                 booking_date DATE,
                 country_id INTEGER,
                 status TEXT,
                 total INTEGER
             );
         ''')

        c.execute('''
             CREATE TABLE my_order_items (
                 id INTEGER PRIMARY KEY,
                 order_id INTEGER,
                 product_id INTEGER,
                 quantity INTEGER,
                 price INTEGER
             );
         ''')

        # Populate tables
        statuses = ['confirmed', 'shipped', 'delivered', 'cancelled']

        for i in range(1, 501):
            booking_date = datetime.now() - timedelta(days=random.randint(0, 60))
            country_id = random.randint(60, 75)
            status = random.choice(statuses)
            total = random.randint(5, 250)

            c.execute('INSERT INTO my_orders VALUES (?, ?, ?, ?, ?)', (i, booking_date, country_id, status, total))

            # For each order, create 1-5 order items
            for j in range(random.randint(1, 5)):
                product_id = random.randint(1, 20)
                quantity = random.randint(1, 10)
                price = random.randint(1, 100)
                c.execute('INSERT INTO my_order_items VALUES (?, ?, ?, ?, ?)',
                          (i * 10 + j, i, product_id, quantity, price))

        # Save (commit) the changes
        conn.commit()

        # Close the connection
        conn.close()

    @staticmethod
    def execute_against_dummy_data(query: str) -> List[Dict]:
        conn = sqlite3.connect('shopy.db')
        c = conn.cursor()
        c.execute(query)
        rows = c.fetchall()
        conn.close()
        return rows

    def test_yaml_loader(self):
        cube_configs = load_cube_configs(dir_path="../cubes")
        self.assertEqual(len(cube_configs), 1)
        self.assertEqual(cube_configs[0]['cubes'][0]['name'], 'orders')

    def test_simple_query(self):
        self.create_dummy_data()
        query = {
            "fields": ["orders.id", "orders.booking_date_day", "orders.country_id", "orders.revenue",
                       "orders.average_order_value_rolling_30_days"],
            "filters": ["${orders.country_id} = '67'"],
            "sorts": ["orders.average_order_value"],
            "limit": 10
        }

        cube_configs = load_cube_configs(dir_path="../cubes")
        sql = generate_sql_query(cube_configs[0], query)
        print(sql)
        result = self.execute_against_dummy_data(sql)
        self.assertGreater(len(result), 3)

        # varation without window and not all fields selected
        print('\n###\n')
        query = {
            "fields": ["orders.id", "orders.booking_date_day", "orders.revenue"],
            "filters": ["${orders.country_id} = '67'"],
            "limit": 10
        }
        sql = generate_sql_query(cube_configs[0], query)
        print(sql)
        result = self.execute_against_dummy_data(sql)
        self.assertGreater(len(result), 3)

        # varation with sort
        print('\n###\n')
        query = {
            "fields": ["orders.booking_date_month", "orders.revenue"],
            "sorts": ["orders.country_id desc"],
            "limit": 10
        }
        sql = generate_sql_query(cube_configs[0], query)
        print(sql)
        result = self.execute_against_dummy_data(sql)
        self.assertGreater(len(result), 2)

    def test_complex_query(self):
        # query = {
        #     "fields": ["orders.booking_date_month", "orders.country_id", "orders.revenue",
        #                "orders.average_order_value_rolling", "orders_items.quantity"],
        #     "filters": ["${orders.country_id} = '67'"],
        #     "sorts": ["orders.booking_date_week"],
        #     "limit": 100
        # }
        query = {
            "fields": ["orders.booking_date_month", "orders.revenue", "orders_items.quantity"],
            "filters": ["${orders.country_id} = '67'"],
            "sorts": ["orders.booking_date_month"],
            # "limit": 2
        }
        cube_configs = load_cube_configs(dir_path="../cubes")
        sql = generate_sql_query(cube_configs[0], query)
        print(sql)
        result = self.execute_against_dummy_data(sql)
        print(result)
        self.assertEqual(len(result), 3)


if __name__ == '__main__':
    unittest.main()
