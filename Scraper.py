from concurrent.futures import ProcessPoolExecutor
import time
import re
import sys
import argparse
import os
import random
import signal
import re


from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm
from urllib.parse import quote_plus

from databaseClasses import PostgressDBConnection, AWSS3Connection
from email.header import Header
from wsgiref import headers
from torpy.http.requests import TorRequests
import urllib.request
import random

load_dotenv()

class Scraper():

    headers = [
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edg/98.0.1108.56",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/98.0.4515.107",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 OPR/98.0.4515.107",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4515.107 Safari/537.36 Edge/98.0.1108.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0"
    ]
    proxies_all = "https://customer-ardaakman:Scriep123@pr.oxylabs.io:7777"
    # Split the proxies into a list, and split each proxy into the relevant fields (username, password, endpoint, port)

    def __init__(self, startingUrl, company, brand_base_url):
        self.company = company
        self.startingUrl = startingUrl
        ## Connect to pg database on aws
        self.pg = PostgressDBConnection(table_name="productdata")
        self.aws = AWSS3Connection()
        self.ignoreUpdates = False
        # Leave empty string, if urls scraped are absolute/have base url.
        self.BRAND_BASE_URL = brand_base_url
        #Read from proxies.txt
        with open("./proxies.txt", "r") as file:
            self.datacenter_proxies = file.readlines()

    def datacenter_proxy(self) -> dict:
        prox_list = [x.strip() for x in self.datacenter_proxies]
        # Select a random proxy
        proxy = random.choice(prox_list)
        provider = {
            "http": f"http://{proxy}",
        }
        # Create the proxy dictionary, return it
        return provider



    def firefox_proxy(self) -> dict:
        # Construct the proxy string with authentication
        #use unix time for random seed.

        # Construct the proxies dictionary
        proxies = {
            "https": self.proxies_all,
            }
            # "no_proxy": 'localhost,127.0.0.1', # Usually not needed in the proxies dictionary

        return proxies

    def create_driver(self):
        
        header = random.choice(self.AGENT_LIST)
        proxy_settings = self.firefox_proxy(header)

        seleniumwire_options = {
            'proxy': {
                'http': proxy_settings["http"],
                'no_proxy': 'localhost,127.0.0.1',
            }
        }

        # If your proxy requires authentication, add the credentials
        if 'username' in proxy_settings and 'password' in proxy_settings:
            seleniumwire_options['proxy']['username'] = proxy_settings['username']
            seleniumwire_options['proxy']['password'] = proxy_settings['password']

        # Configure additional options for Chrome
        chrome_options = webdriver.ChromeOptions()
        # chrome_options.add_argument(f'user-agent={header}')
        # prefs = {"profile.managed_default_content_settings.images": 2}
        # chrome_options.add_experimental_option("prefs", prefs)

        # Initialize the WebDriver with the specified options
        driver = webdriver.Chrome(
            seleniumwire_options=seleniumwire_options,
            chrome_options=chrome_options
        )
        return driver

    def scrapeProducts(self, fn):
        """Function that scrapes the actual urls from a website and returns this."""
        if not(self.ignoreUpdates):
            old_products = self.pg.run_query(f"SELECT url FROM productdata WHERE brand = '{self.company}'")
            #set of old product urls
            old_set = set(old_products[:,0])
        else:
            old_set = set()
        urls = self.pg.run_query(f"SELECT url FROM producturls WHERE brand = '{self.company}'")
        urls = urls[:,0]
        urls = [url for url in urls if self.BRAND_BASE_URL + url not in old_set]
        #This trial, just give random url.
        cols  = ['name', 'gender', 'color', 'description', 'compositions', 'price', 'sizes', 'images', 'url', 'brand']
        prods = fn(urls)
        # save prods into db
        self.saveProduct(prods, cols)
    

    def scrapeUrls(self, fn):
        # print("here?")
        connection_established = self.pg.test_connection()
        if not connection_established:
            print("Could not establish connection to database. Exiting...")
            sys.exit(1)
        
        if not(self.ignoreUpdates):
            old_products = self.pg.run_query(f"SELECT url FROM producturls WHERE brand = '{self.company}'")
            #set of old product urls
            old_set = set(old_products[:, 0])
        else:
            old_set = set()

        urls = fn(self.startingUrl)
        result_urls = []
        for url in urls:
            if url not in old_set:
                result_urls.append([url, self.company])
        # [url1, url2, url3] --> # [[url1, brand], [url2, brand], [url3, brand]]
        #Save this in pg database
        self.saveUrls(result_urls, ["url", "brand"])
        return result_urls
    

    def fetchProductsFromDb(self):
        query = f"SELECT * FROM products WHERE company = '{self.company}'"
        return self.pg.run_query(query)
    
    
    def process_urls_in_chunk(self, urls_chunk, mapping, i, lock):
            sub_chunk_size = 5  # Number of URLs to process before switching session
            # Break the urls_chunk into smaller sub-chunks
            for sub_start in range(0, len(urls_chunk), sub_chunk_size):
                sub_chunk = urls_chunk[sub_start:sub_start + sub_chunk_size]
                subchunk_processed_count = 0
                vals = []
                with TorRequests() as tor_requests:
                    with tor_requests.get_session() as sess:
                        HEADERS = {"User-Agent": random.choice(self.AGENT_LIST)}
                        print(sess.get("http://httpbin.org/ip").json())
                        print(HEADERS["User-Agent"])
                        for url in tqdm(sub_chunk):
                            bs = BeautifulSoup(sess.get(url).text, 'html.parser')
                            val = self.scrapeSingleProduct(bs, url)
                            vals.append(val)
                #Store vals in database.
                self.pg.save_product_details(vals)
                print(f"Subchunk {i} processed {subchunk_processed_count} urls")

    def saveUrls(self, urls, columns):
        """Function that saves the urls to the database."""
        self.pg.save_data_to_db("producturls", urls, columns)

    def saveProduct(self, product, columns):
        """"Here are the columns:
                'Unique ID': sha256_hash,
                'Color': product_color,
                'Name': product_name,
                'Description': product_long_desc,
                'Details': product_details,
                'Material': material_type,
                'Image_urls': secondary_image_urls,
                'Product_url': color_url,
                'Size': size,
                'Size Availability': availability,
                'Gender': gender,
                'Price': product_price,
            """
        self.pg.save_data_to_db("productdata", product, columns)


    def scrapeSingleProduct(self, driver,  url , fn):
        """"This function should get the details of the product. The requred fields are:
        - product_name
        - product_color
        - product_description
        - avaliable_sizes
        - Material information
        - image_urls
        Function can change per website.
        """
        return fn(driver, url)
    
    def create_listener(self):
        self.pg.conn.autocommit = True
        curs = self.pg.conn.cursor()
        curs.execute("LISTEN productdata_channel;")
        print("Listening for notifications on channel 'productdata_channel'")

        try:
            while True:
                # Check for connection status here
                print("Waiting for notifications...")

                self.pg.conn.poll()
                while self.pg.conn.notifies:
                    notify = self.pg.conn.notifies.pop(0)
                    print(f"Received notification: {notify.payload}")
                    # Run the image update function here
                    self.aws.upload_images_to_s3(self.company, self)

                # Sleep for a short period to prevent high CPU usage, adjust the time as needed
                time.sleep(5)
        except Exception as e:
            print(f"An error occurred: {e}")




    






