import argparse
from concurrent.futures import ProcessPoolExecutor
import time
import re
import sys
import hashlib
import os
import random
import re
import requests
import json5
import json


import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm
from torpy.http.requests import TorRequests
from email.header import Header
from wsgiref import headers
from torpy.http.requests import TorRequests
from requests.exceptions import SSLError, HTTPError
from urllib.parse import urlparse, urlunparse


from databaseClasses import PostgressDBConnection
from Scraper import Scraper


load_dotenv()


ZARA_START_URL = "https://www.zara.com/us/en/categories?ajax=true"
ZARA_BASE_URL = "https://www.zara.com/us/en/"

def find_hrefs(soup, path):
    vals = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(path)]
    return set(vals)


def setup_session(scraper):
    header = scraper.get_browser_header()
    session = requests.Session()
    session.headers.update(header)
    session.proxies.update(scraper.get_proxy())
    return session

def get_categories(json_data):
    category_urls = []
    category_ids = []
    for category in json_data.get("categories", []):
        for subcategory in category.get("subcategories", []):
            id = subcategory.get("id")
            seo = subcategory.get("seo", {})  # Access the "seo" object
            seo_category_id = seo.get("seoCategoryId")
            keyword = seo.get("keyword")
            category_url = f"{ZARA_START_URL}en/{keyword}-l{seo_category_id}.html?ajax=true"
            category_urls.append(category_url)
            category_ids.append(id)
    
    return category_urls, category_ids

def get_urls(scraper, category_url):
    session = setup_session(scraper)
    response = session.get(category_url)

    while response.status_code != 200:
        print("Failed to get URL:", category_url, "Status Code:", response.status_code)
        time.sleep(2 if response.status_code == 403 else 1)
        session = setup_session(scraper)
        response = session.get(category_url)

    category_data = response.json()
    # Extract product links from the category data and construct product links
    product_links = []
    for product in category_data.get("productGroups", []):
        for element in product.get("elements", []):
            if "commercialComponents" in element:
                for component in element["commercialComponents"]:
                    if component["type"] == "Product":
                        keyword = component["seo"]["keyword"]
                        seo_product_id = component["seo"]["seoProductId"]
                        product_link = f"https://www.zara.com/us/en/{keyword}-p{seo_product_id}.html?ajax=true"
                        timestamp = time.time()
                        product_links.append([product_link, timestamp])
    return product_links


def scrape_urls_zara(scraper: Scraper, url: str, base_url: str) -> list:
    try:
        session = setup_session(scraper)
        zara_request = session.get(url)
        while zara_request.status_code != 200:
            print("Failed to get URL:", url, "Status Code:", zara_request.status_code)
            time.sleep(2 if zara_request.status_code == 403 else 1)
            session = setup_session(scraper)
            zara_request = session.get(url)
            print(zara_request.headers)
            print(session.headers)
        json_data= zara_request.json()
        _, category_ids = get_categories(json_data)

        all_links = []
        pbar = tqdm(total=len(category_ids), desc="Scraping Zara Product Urls", leave=True)
        for category_id in category_ids:
            category_url = f"https://www.zara.com/us/en/category/{category_id}/products?regionGroupId=8&ajax=true"
            product_links = get_urls(scraper, category_url)
            all_links.extend(product_links)
            pbar.update(1)
        
        pbar.close()
        print("Finished scraping Zara product urls!")
        print(all_links[0])
        return all_links
    
    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except SSLError as ssl_err:
        print(f"SSL error occurred: {ssl_err}")
    except Exception as err:
        print("weird error")
        print(f"An error occurred: {err}")

    return []


def get_price(p):
    price = str(p)
    if len(price) >= 2:
        price = price[:-2] + "." + price[-2:]
    return price

def get_material(scraper, id):
    material_url = f"https://www.zara.com/us/en/product/{id}/extra-detail?ajax=true"
    session = setup_session(scraper)
    response = session.get(material_url)
    materials = []
    if response.status_code == 200:
        material_info = json5.loads(response.text)
        for section in material_info:
            if section.get("sectionType") in ["materials", "composition"]:
                for component in section.get("components"):
                    if "datatype" in component and component["datatype"] == "paragraph":
                        text = component["text"]["value"]
                        if "%" in text:
                            materials.append(text)
        return ', '.join(materials)

def get_image_urls(json_data):
    base_url = "https://static.zara.net/photos/"
    image_urls = []
    xmedia = json_data.get("xmedia", [])  # Get the "xmedia" array
    for img_info in xmedia:
        if img_info.get("datatype") == "xmedia" and img_info.get("type") == "image":
            path = img_info.get("path")
            name = img_info.get("name")
            timestamp = img_info.get("timestamp")
            image_url = f"{base_url}{path}/w/563/{name}.jpg?ts={timestamp}"
            image_urls.append(image_url)
    return image_urls


def get_sizes(color):
    sizes = color["sizes"]
    size_availabilities = []
    for size in sizes:
        size_name = size["name"]
        availability = size["availability"]
        size_availability = f"{size_name}, {availability}"
        size_availabilities.append(size_availability)
    return size_availabilities

def get_gender(product_json):
    gender = product_json['product']['sectionName']
    gender = gender.lower()
    if gender == "woman":
        return "women"
    elif gender == "man":
        return "men"
    elif gender == 'kid':
        return "kid"
    else:
        return "unisex"

def get_product_url(product_json, i):
    url = product_json['productMetaData'][i]['url']
    return url

def get_product_brand(product_json, i):
    brand = product_json['productMetaData'][i]['brand']
    if brand == "MASSIMODUTTI":
        brand = "massimo dutti"
    return "zara"



def get_product_data(scraper, product_json, product_link):
    product_name = product_json["product"]["name"]
    colors = [color["name"] for color in product_json["product"]["detail"]["colors"]]
    desc = product_json["productMetaData"][0]["description"]
    material = get_material(scraper, product_json["product"]["detail"]["colors"][0]["productId"])
    price = get_price(product_json["product"]["detail"]["colors"][0]["price"])
    image_urls = [get_image_urls(color) for color in product_json["product"]["detail"]["colors"]]
    sizes = [get_sizes(color) for color in product_json["product"]["detail"]["colors"]]
    gender = get_gender(product_json)
    urls = [get_product_url(product_json, i) for i in range(len(product_json['productMetaData']))]
    brands = [get_product_brand(product_json, i) for i in range(len(product_json['productMetaData']))]

    #Pack all of these into rows.
    rows = []
    time_now = time.time()
    # Do this in format of mapping within the list below.

    for i in range(len(colors)):
        rows.append({
            "name": product_name,
            "color": colors[i],
            "description": desc,
            "composition": material,
            "price": price,
            "images": image_urls[i],
            "sizes": sizes[i],
            "time_now": time_now,
            "gender": gender,
            "brand" : brands[i],
            "url": urls[i],
        })

    return rows

def format_dictionary_data(product_data):
    new_rows = []
    seen_so_far = set()
    for row in product_data:
        if row["url"] in seen_so_far:
            continue
        seen_so_far.add(row["url"])
        # Format images the right way first, i.e seperated by |
        images = row["images"]
        
        #Replace https with http
        for i in range(len(images)):
            images[i] = images[i].replace("https", "http")

        images_formatted = "|".join(images)
        new_rows.append([row["name"], row["gender"], row['color'], row['description'], row['composition'], row['price'], row['sizes'], images_formatted, row['url'], row['brand'], row['time_now']])
    return new_rows

def scrape_items_zara(scraper: Scraper, urls: list) -> list:
    """Function that scrapes the items from the urls."""
    # Create a session and get the urls
    session = setup_session(scraper)
    failed_urls = []
    items = []
    pbar = tqdm(total=len(urls), desc="Scraping Zara Products", leave=True)
    count = 0
    for url in urls:
        if count % 25 == 0 and count != 0:
            # Wait extra now and then.
            time.sleep(3)
        if count % 50 == 0 and count != 0:
            session = setup_session(scraper)
            scraper.save_product(items)
            items = []

        try:
            response = session.get(url)
            while response.status_code != 200:
                print("Failed to get data:", url, "Status Code:", response.status_code)
                time.sleep(2 if response.status_code == 403 else 1)
                session = setup_session(scraper)
                response = session.get(url)

            product_json = json5.loads(response.text)
            product_data = get_product_data(scraper, product_json, url)
            formatted_data = format_dictionary_data(product_data)

            items.extend(formatted_data)
            pbar.update(1)
            count+=1
        except Exception as err:
            print(f"An error occurred: {err}")
            failed_urls.append(url)
            continue
    
    pbar.close()
    save_failed_urls(failed_urls)
    return items


def save_failed_urls(failed_urls):
    # Read from the file, then write to file without duplicates.
    with open('failed_urls.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            failed_urls.append(line.strip())
    
    failed_urls = list(set(failed_urls))

    with open('failed_urls.txt', 'w') as f:
        for url in failed_urls:
            f.write("%s\n" % url)



def main(scrape_urls_flag, scrape_products_flag, use_residential_proxy):
    if scrape_urls_flag:
        # Scrape both women and men urls. For zara, this id done in one function!
        scraper = Scraper(ZARA_START_URL, "zara", ZARA_BASE_URL, use_residential_proxy)
        scraper.scrape_urls(lambda x, y: scrape_urls_zara(scraper, x, y))
        scraper.pg.remove_url_duplicates("zara", "producturls")
        scraper.kill_db_connection()

    if scrape_products_flag:
        # Scrape product details.
        scraper = Scraper(ZARA_START_URL, "zara", ZARA_BASE_URL, use_residential_proxy)
        scraper.scrape_products(lambda x: scrape_items_zara(scraper, x))
        scraper.pg.remove_product_duplicates("zara", "productdata")
        scraper.kill_db_connection()

    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web scraping script for H&M products.')

    # Define the three arguments
    parser.add_argument('--scrape-urls', action='store_true', help='Scrape URLs if set')
    parser.add_argument('--scrape-products', action='store_true', help='Scrape products if set')
    parser.add_argument('--residential-proxy', action='store_true', help='Use residential proxies if set')

    # Parse the arguments
    args = parser.parse_args()
    # Write to random file to test if this works.
    with open('test.txt', 'w') as f:
        f.write("Hello World")

    # Call the main function with the parsed arguments
    main(args.scrape_urls, args.scrape_products, args.residential_proxy)


    