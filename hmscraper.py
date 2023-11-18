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


from databaseClasses import PostgressDBConnection
from Scraper import Scraper


load_dotenv()



HM_BASE = "https://www2.hm.com"

def find_hrefs(soup, path):
    vals = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(path)]
    return set(vals)

def pick_random_proxy(scraper: Scraper):
    return scraper.firefox_proxy()


def scrape_all(scraper: Scraper, url: str, ) -> list:
    # Some required constants that will help with scraping
    HM_BASE = "https://www2.hm.com"
    hm_query = "?page-size=1000"
    match_string = "/en_us/productpage."


    agent_used = random.choice(scraper.headers)
    proxy = pick_random_proxy(scraper)
    headerUsed = {
        'User-Agent': agent_used,
        'origin': 'https://www2.hm.com'
    }
    session = requests.Session()
    session.headers.update(headerUsed)
    session.proxies.update(proxy)
    all_urls = []
    failed_urls = []
    try:
        #Grab all the group links first for the categories!
        response = session.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        span = soup.find_all('span', string="Shop by Product")
        if "women" in url:
            ul = span[0].find_next_sibling('ul')
        else:
            ul = span[1].find_next_sibling('ul')

        # Extract each <li> element from the <ul>
        li_elements = ul.find_all('li')

        # Get the text and href for each <li>
        li_data = [{'text': li.get_text(strip=True), 'href': li.a['href']} for li in li_elements][1:]

        #Now, loop through each category and grab the subcategories!
        all_urls = []
        k = 0
        while k < len(li_data):
            print(k, len(li_data))
            data = li_data[k]
            _, href = data['text'], data['href']
            response = session.get(HM_BASE + href)
            if response.status_code != 200:
                print("Could not get url!", full_url, flush=True)
                failed_urls.append(full_url)
                if response.status_code == 403:
                    time.sleep(2)
                else:
                    time.sleep(1)
                    k+= 1
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            #Remvoe the html part
            vals = find_hrefs(soup, href[:-5])
            all_urls.extend(list(vals))
            k += 1
        cleaned_urls = [url for url in all_urls if '&' not in url]
        cleaned_urls = [url for url in all_urls if '?' not in url]

        # We have gotten all the urls! Now, lets loop a little bit, while using a proxy to make sure 
        #our addresses being hidden.
        i = 1
        all_urls = []
        proxy = pick_random_proxy(scraper)
        random.seed(time.time())
        while i < len(cleaned_urls):
            print(i, len(cleaned_urls))
            time.sleep(0.5)
            if i % 20 == 0:
                time.sleep(2)
            full_url = HM_BASE + cleaned_urls[i] + hm_query
            proxy = pick_random_proxy(scraper)
            agent_used = random.choice(scraper.headers)
            headerUsed = {
                'User-Agent': agent_used,
                'origin': 'https://www2.hm.com',
            }
            session.headers.update(headerUsed)
            session.proxies.update(pick_random_proxy(scraper))
            response = session.get(full_url, headers=headerUsed, proxies=proxy)
            if response.status_code != 200:
                print("Could not get url!", full_url, flush=True)
                failed_urls.append(full_url)
                if response.status_code == 403:
                    time.sleep(10)
                else:
                    time.sleep(1)
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            vals = find_hrefs(soup, match_string)
            all_urls.extend(list(vals))
            i += 1

    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")  # e.g., 404, 501, etc
    except SSLError as ssl_err:
        print(f"SSL error occurred: {ssl_err}")
    except Exception as err:
        print(f"An error occurred: {err}")
    #Save the urls in a database table, just in case to save progress.
    # Save also locally just in case (for first iteration!)
    return all_urls


def remove_trailing_commas(json_string):
    # This pattern finds a comma followed by any amount of whitespace and then a closing brace or bracket
    pattern = r',\s*([}\]])'
    # Replace any matches with just the closing brace or bracket
    return re.sub(pattern, r'\1', json_string)


def scrape_items(scraper: Scraper, urls : list[str]):
    # Get the urls from the database, using the connection through scraper.
    # Then, loop through each url, and scrape the data.
    # Start session for request, also obtain header and proxy.
    session = requests.Session()
    failed_urls = []
    rows = []
    i = 0
    # Now, loop through each url, and scrape the data. Do while loop, so that if there is an error, we can try again.

    # TODO: CREATE A TQDM PROGRESS BAR WITH LEN(URLS) AS THE TOTAL

    # Create a tqdm progress bar with len(urls) as the total
    pbar = tqdm(total=len(urls), desc="Scraping HM Products", leave=True)
    count = 0
    failed_urls = []
    while i < len(urls):
        # print("Progress: ", i/len(urls) * 100, "%", flush=True)
        if i % 40 == 0 and i != 0:
            time.sleep(2)
            scraper.saveProduct(rows, columns)
            rows = []
        full_url = HM_BASE + urls[i]
        proxy = pick_random_proxy(scraper)
        agent_used = random.choice(scraper.headers)
        headerUsed = {
            'User-Agent': agent_used,
            'origin': 'https://www2.hm.com',
        }
        session.headers.update(headerUsed)
        session.proxies.update(pick_random_proxy(scraper))
        print(session.proxies)
        try:
            response = session.get(full_url, headers=headerUsed, proxies=proxy)
        except:
            failed_urls.append(full_url)
            i+= 1
            continue
        if response.status_code != 200:
            print("Could not get url!", full_url, flush=True)
            if response.status_code == 403 and count < 3:
                count+= 1
                time.sleep(3)
            elif count == 3:
                count = 0
                failed_urls.append(full_url)
                i+=1
            else:
                time.sleep(2)
            continue
        # Call the scrape_item function, which will return a list of values for the row.
        # If the function returns false, then we have an error, so we will try again.
        truth = scrape_item(full_url, rows, response)

        # TODO: INCREMENT TWDM PROGRESS BAR HERE

        if not(truth):
            failed_urls.append(full_url)
        pbar.update(1)  # Increment the tqdm progress bar
        i+=1
        count = 0 
    #save failed urls locally.
    # Now, we have all the rows, so we can save them to the database.
    # We input saved rows into database as a list of lists, where each list is a row.
    # We also save the failed urls to a file, so that we can try again later.
    # Save the rows to the database
    # Save the failed urls to a file using python file write
    with open('failed_urls.txt', 'w') as f:
        for url in failed_urls:
            f.write("%s\n" % url)
    return rows


def scrape_item(url, lst, response, count = 0):
    soup = BeautifulSoup(response.text, "html.parser")
    #Save the soup result in an output file.
    with open('output.html', 'w') as file:
        file.write(str(soup))
    # Now, we need to extract the script tag that contains the productArticleDetails
    script_tag = soup.find('script', text=re.compile('productArticleDetails'))
    pattern = re.compile(r'var productArticleDetails = ({.*?});', re.DOTALL | re.MULTILINE)
    script_content = script_tag.string if script_tag else ''
    match = pattern.search(script_content)
    if match:
        try:
            # Extract the JavaScript object
            json_string = match.group(1)
            # Since the JavaScript object is not valid JSON (it may contain single quotes, comments, etc.),
            # you may need to perform some cleanup here before loading it as JSON.
            # This step highly depends on the content. As an example, I'm replacing single quotes with double quotes:
            json_string = json_string.replace("'", '"')
            json_string = re.sub(r"^$", "", json_string)
            pattern = r'"images":\[.*?\],'
            matched_pattern = re.search(pattern, json_string, flags=re.DOTALL)
            matched_pattern = matched_pattern[0][:-1]
            new_pattern = r'isDesktop \? "([^"]+)"'
            #Match new pattern to get
            new_matches = re.findall(new_pattern, matched_pattern, flags=re.DOTALL)

            
            # Replace the matched "images" part with an empty string
            cleaned_string = re.sub(pattern, '', json_string, flags=re.DOTALL)
            marketing_pattern = r'"marketingMarkers":\s*\[[^\]]*?\],'
            marketing_match = re.findall(marketing_pattern, cleaned_string, flags=re.DOTALL)
            if marketing_match:
                cleaned_string = re.sub(marketing_pattern, '', cleaned_string, flags=re.DOTALL)
            data = json5.loads(cleaned_string)

            # Reformat it using the standard json library to fix formatting
            fixed_json_string = json.dumps(data, indent=4)
            product_article_details = json.loads(fixed_json_string)
            keys = []
            for key in product_article_details.keys():
                # Check if the key is numeric (e.g., "1207580001" and "1207580002")
                if key.isdigit():
                    # Access the numeric sub-object
                    keys.append(key)
            name = product_article_details['alternate']
            gender = product_article_details['alternate'].split(" ")[-4]
            code = product_article_details['articleCode']
            for key in keys:
                general = product_article_details[key]
                color = general['name']
                desc = general['description']
                compositions = str(general['compositions'])
                price = general['whitePrice']
                sizes = [size['name'] for size in general['sizes']]
                images = new_matches
                lst.append([name,gender, color, desc, compositions, price, sizes, images, url, 'hm'])
        except Exception as e:
            print("Error in scraping item!", e, flush=True)
            return False

        # Return these values in forms of rows - each row contains the data for one item.
        # There are more than 1 values for some of the columns, such as images or sizes.
        # So for example, images contains multiple values. So do sizes. Concatenate these values in a format a database woudl accept.
        # Images can be | seperated, so can sizes.
        # The rest are just strings.
        images = "|".join(images)
        sizes = "|".join(sizes)
        # Now formulate into a row, where the above order to derive the elements is followed
        lst.append([name,gender, color, desc, compositions, price, sizes, images, url, 'hm'])
        return True
    else:
        print("No productArticleDetails found in the script tag.")
        return False

if __name__ == '__main__':
    # Save all urls for women first.
    women_url = "https://www2.hm.com/en_us/women/products/view-all.html"
    scraper = Scraper(women_url, "hm", "https://www2.hm.com")
    women_results = scraper.scrapeUrls(lambda x: scrape_all(scraper, x))
    time.sleep(10)
    men_url = "https://www2.hm.com/en_us/men/products/view-all.html"
    scraper = Scraper(men_url, "hm", "https://www2.hm.com")
    # men_results = scraper.scrapeUrls(lambda x: scrape_all(scraper, x))
    # Remove duplicates if we added any.
    scraper.pg.remove_duplicates_in_database("hm", "producturls")
    scraper.pg.remove_duplicates_in_database("hm", "productdata")
    #Now scrape all items!
    
    scraper.scrapeProducts(lambda x: scrape_items(scraper, x))


    