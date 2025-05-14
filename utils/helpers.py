import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Assuming your custom logging setup is compatible
from logs.custom_logging import setup_logging
import logging, pprint
logger = setup_logging(console_level=logging.DEBUG)

import aiohttp, time, traceback
from parsel import Selector
from typing import Dict, Optional, List, Any
import random
import json, csv
import asyncio
from datetime import datetime


# ========================================================================
# Html Page Scraper class for requesting html using reverse engineering.
# ========================================================================


class HtmlPageScraper:
    """Class for making HTTP requests to fetch contract information from the website."""
    
    def __init__(self):
        """Initialize the HtmlPageScraper with necessary URLs, headers and request parameters."""
        self.logger = logger
        self.base_url = "https://www.walmart.com/search"
        self.proxy_url = "http://brd-customer-hl_62799e1a-zone-us_proxy:wdzfajt8yw6c@brd.superproxy.io:33335"

                    
    def get_fake_header(self) -> Dict[str, str]:
        """
        Generate a random user agent and accept headers for HTTP requests.

        Returns:
            Dictionary containing user agent and accept headers
        """
        try:
            with open("utils/fake_headers.json", "r") as f:
                fake_headers = json.load(f)
                random_browser = random.choice(list(fake_headers.keys()))
                return fake_headers[random_browser]
        except Exception as e:
            self.logger.error(f"❌ Error in get_fake_header: {e}")
            self.logger.debug(traceback.format_exc())
            return {}

    async def request_html(self, params:Dict) -> Optional[str]:
            
        start_time = time.perf_counter()
        retries = 1
        while retries < 3:
            async with aiohttp.ClientSession(proxy=self.proxy_url) as session:
                try:
                    response = await session.get(self.base_url, headers=self.get_fake_header(), params=params, ssl=False, timeout=60)
                    html_content = await response.text()

                    # Calculate and log performance metrics
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    if response.status == 200 and len(html_content) > 2000:
                        self.logger.info(
                            f"Page '{params.get('page')}' for query '{params.get('q')}' fetched successfully ✅ - Status: {response.status}, "
                            f"Length: {len(html_content)}, Time taken: {duration:.2f} seconds"
                        )
                        return html_content
                    else:
                        self.logger.warning(
                            f"Page '{params.get('page')}' for query '{params.get('q')}' fetched with issues ❌ - Status: {response.status}, "
                            f"Length: {len(html_content)}, Time taken: {duration:.2f} seconds"
                        )
                        
                
                except aiohttp.ClientError as e:
                    self.logger.error(f"❌ HTTP client error during fetching: {e}")
                    self.logger.debug(traceback.format_exc())

                except Exception as e:
                    self.logger.error(f"❌ Unexpected error during fetching: {e}")
                    self.logger.debug(traceback.format_exc())

                retries += 1
                self.logger.debug(f"Retrying... {retries}/3")

  

# ==========================================
# Html Parser to extract structured data
# ==========================================
          

class HtmlParser:
    """Parser for extracting product information from Walmart HTML pages."""
    
    def __init__(self):
        """Initialize parser with configuration."""
        self.base_url = "https://www.walmart.com"
        self.logger = logger

    def _find_products_in_json(self, obj: Any, typename: str = "Product") -> List[Dict]:
        """
        Recursively search for product data in nested JSON structure.

        Args:

            obj: JSON object to search
            typename: The typename to match in the data
            
        Returns:
            List[Dict]: Matching product objects
        """
        matches = []

        if isinstance(obj, dict):
            # Check if current dict is a product
            if obj.get("__typename") == typename:
                matches.append(obj)
            # Search nested dicts
            for value in obj.values():
                matches.extend(self._find_products_in_json(value, typename))

        elif isinstance(obj, list):
            # Search through list items
            for item in obj:
                matches.extend(self._find_products_in_json(item, typename))

        return matches
    
    def _extract_products_by_html(self, selector:Selector):
        products = []
        carts_container = selector.xpath('.//div[@role="group"]')
        if not carts_container:
            return []
        for cart in carts_container:
            try:

                try:
                    price = cart.xpath('.//div[@data-automation-id="product-price"]//span[contains(@class, "f2")]/text()').re(r'\d+')[0]
                    price = float(price)
                except (ValueError, TypeError):
                    continue

                name = cart.xpath('./a/span/text()').get()
                url = cart.xpath('./a/@href').get()

                # Ensure URL is absolute
                if not url.startswith(("http://", "https://")):
                    url = self.base_url + (url if url.startswith("/") else f"/{url}")

                products.append({
                        "name": name,
                        "price": price,
                        "url": url.split("?")[0],  # Remove query parameters
                    })
            except Exception as e:
                    self.logger.error(f"❌ Error extracting product info in html selector method: {str(e)}")
                    continue
            
        return products

    def _extract_products_by_json(self, json_script_tag) -> Optional[Dict]:
        """
        Extract relevant fields from product data.

        Args:
            product_data: Raw product data dictionary
            
        Returns:
            Optional[Dict]: Cleaned product information or None if invalid
        """
        products = []

        try:
            json_data = json.loads(json_script_tag)
        except json.JSONDecodeError:
            self.logger.error("❌ Invalid JSON in script tag")
            return []
        
        product_data_list = self._find_products_in_json(json_data)
        for product_data in product_data_list:
            try:
                # Required fields
                name = product_data.get("name")
                price = product_data.get("price")
                url = product_data.get("canonicalUrl")

                if not all([name, price, url]):
                    continue

                # Clean and validate the data
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    continue

                # Ensure URL is absolute
                if not url.startswith(("http://", "https://")):
                    url = self.base_url + (url if url.startswith("/") else f"/{url}")
                
                products.append({
                    "name": name,
                    "price": price,
                    "url": url.split("?")[0],  # Remove query parameters
                })

            except Exception as e:
                self.logger.error(f"❌ Error extracting product info in json method: {str(e)}")
                continue

        return products


    def search_page_parser(self, html_contents: List[str], query:str) -> List[Dict]:
        """
        Parse product information from multiple HTML pages.

        Args:
            html_contents: List of HTML page contents to parse
            
        Returns:
            List[Dict]: List of parsed product information
        """
       
        
        try:
            for html_content in html_contents:
                if not html_content:
                    continue

                selector = Selector(html_content)
                json_script_tag = selector.xpath(
                    './/script[@id="__NEXT_DATA__" and @type="application/json"]/text()'
                ).get()

                if not json_script_tag:
                    products = self._extract_products_by_html(selector)
                
                products = self._extract_products_by_json(json_script_tag)
                    
            return products

        except Exception as e:
            self.logger.error(f"❌ Error in search_page_parser: {str(e)}")
            self.logger.debug(traceback.format_exc())
            return []
    

# ==================================================
# Input/Output Functions for saving & loading data
# ==================================================

def load_input_data(
    input_csv_path: str = 'input_data/products_details.csv',
    output_json_path: Optional[str] = 'input_data/products_details.json',
    required_fields: List[str] = ['Item Name', 'Min Cost ($)', 'Max Cost ($)']
) -> List[Dict[str, Any]]:
    """
    Load product data from a CSV file and convert it to a list of dictionaries.
    Optionally save the converted data to a JSON file.
    
    Args:
        input_csv_path: Path to the input CSV file
        output_json_path: Path to save the JSON output (None to skip saving)
        required_fields: List of required fields in the CSV
        
    Returns:
        List of product dictionaries with standardized structure
        
    Raises:
        FileNotFoundError: If the input CSV file does not exist
        ValueError: If the CSV is missing required fields or contains invalid data
    """
    products = []
    row_count = 0
    error_count = 0
    
    # Check if file exists
    if not os.path.exists(input_csv_path):
        error_msg = f"Input CSV file not found: {input_csv_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    try:
        with open(input_csv_path, 'r', encoding='utf-8') as file:
            # Read the CSV file
            csv_reader = csv.DictReader(file)
            
            # Validate headers
            headers = csv_reader.fieldnames
            if not headers:
                raise ValueError("CSV file appears to be empty or has no headers")
            
            # Check if all required fields are present
            missing_fields = [field for field in required_fields if field not in headers]
            if missing_fields:
                raise ValueError(f"CSV is missing required fields: {', '.join(missing_fields)}")
            
            # Process each row
            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is headers
                row_count += 1
                try:
                    # Validate and extract required data
                    item_name = row.get('Item Name', '').strip()
                    if not item_name:
                        logger.warning(f"Row {row_num}: Missing item name, skipping")
                        error_count += 1
                        continue
                    
                    # Convert price values to float and handle errors
                    try:
                        min_price = float(row.get('Min Cost ($)', '0').strip())
                    except ValueError:
                        logger.warning(f"Row {row_num}: Invalid min price for '{item_name}', using 0")
                        min_price = 0
                        error_count += 1
                    
                    try:
                        max_price = float(row.get('Max Cost ($)', '0').strip())
                    except ValueError:
                        logger.warning(f"Row {row_num}: Invalid max price for '{item_name}', using 0")
                        max_price = 0
                        error_count += 1
                    
                    # Ensure min_price is not greater than max_price
                    if min_price > max_price:
                        logger.warning(
                            f"Row {row_num}: Min price (${min_price}) > Max price (${max_price}) "
                            f"for '{item_name}', swapping values"
                        )
                        min_price, max_price = max_price, min_price
                        error_count += 1
                    
                    # Create product dictionary with standardized structure
                    product_info = {
                        "product_name": item_name,
                        "min_price": min_price,
                        "max_price": max_price,
                        # "original_row": row_num  # Keep track of source row for debugging
                    }
                    
                    # Add any additional fields that might be useful
                    for key, value in row.items():
                        if key not in ['Item Name', 'Min Cost ($)', 'Max Cost ($)'] and value.strip():
                            product_info[key.lower().replace(' ', '_')] = value.strip()
                    
                    products.append(product_info)
                    
                except Exception as e:
                    logger.error(f"Error processing row {row_num}: {e}")
                    error_count += 1
        
        # Save to JSON if output path is provided
        if output_json_path and products:
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
                
                with open(output_json_path, 'w', encoding='utf-8') as json_file:
                    json.dump(products, json_file, indent=4)
                logger.info(f"Successfully saved {len(products)} products to {output_json_path}")
            except Exception as e:
                logger.error(f"Failed to save JSON output: {e}")
        
        # Log summary
        logger.info(f"Processed {row_count} rows with {error_count} errors, loaded {len(products)} valid products")
        
        return products
        
    except Exception as e:
        logger.error(f"Failed to load data from CSV: {e}")
        raise

def save_output_data(data: List[Dict[str, Any]]) -> None:
    """
    Save the output data to a JSON file.
    
    Args:
        output_json_path: Path to save the JSON output
        data: List of dictionaries containing product information
    """
    try:
        final_data = {}
        output_path = 'output_data\scraped_products.json'
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        for item in data:
            product_name = item.get("product_name").lower().replace(" ", "_").replace(",", "_").replace("'", "_")
            if product_name:
                final_data[product_name] = item


        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(final_data, json_file, indent=4, ensure_ascii=False)
        logger.info(f"Successfully saved {len(final_data)} products to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save JSON output: {e}")




# ==================================================
# Generate walmart_cookies.json file from raw cookie
# ==================================================


def get_cookies():

    try:
        cookies = {
        '_pxhd': '8719f7fa89794a4e0ed240b2ba529fddcc96acab258d83b29af68ce97efc4d99:f7a6db8b-2cfe-11f0-93a9-996323160e01',
        'io_id': 'e332f145-d7bc-4f3b-a298-8624c447edaa',
        '_pxvid': 'f7a6db8b-2cfe-11f0-93a9-996323160e01',
        'AID': 'wmlspartner=0:reflectorid=0000000000000000000000:lastupd=1746855634737',
        '_m': '9',
        'userAppVersion': 'usweb-1.200.0-3cf07f198a24f446ffc19881299dca1235c19726-5081358r',
        'abqme': 'true',
        'vtc': 'RK8oFWsrX2CNmeRZRsehxE',
        'adblocked': 'false',
        'hasLocData': '1',
        '_intlbu': 'false',
        '_shcc': 'US',
        'bstc': 'ZbYAZl-zasICcUHuVM4qrU',
        'isoLoc': 'PK_',
        'pxcts': 'fe4e4d52-3079-11f0-977c-f5d173cdbc5a',
        'bm_mi': '704208FC89C6E7F49410928278BE96E3~YAAQBuscuLY4eYmWAQAAGKMBzRuRPA2fIDrv88afLNTRu/QGjJsJaLy7yz8erbaC2KtiN5jYoOAjTIdgDCVhV7IUHDwEottiVe/4Ht0SNzKVtttuhTmXkhEzDiluRyuMWiZVCKuz6n1UM3AEwgU+dwd9T8+y8hco+W5takXnRuLUQqndrtBlIDaZ4oFdq68l1h6luTQc16GOWj6UOY9YzAdv5DQa48B09I4QIx0ymqcjtAvoM9Jvf+QWQzHNaOv/jUxsQ6ohdokGj1k43dgtMM22NaEuQMmydprLLd5+jrpAHQeTl6vWwHA6hASAHifksN2MsXlCENCveLAgtcdp2+wOMFAokMKUQ/SYSgQ/d0j0LKvthH8vOtJFXWTkHo76NxDUifIlBV05PfcZD0JhLvtovDnO3MXRSsyeasM=~1',
        'bm_sv': '24FC5286FEF44A6079AAE15FCEC9F766~YAAQBuscuBA6eYmWAQAA374BzRv4m0E2Poz9FFQX3UjjwpxqlM2Q+8yFD8e6Vj0ThnNPsvc/dbGakDrTy6PUtlOyMe3YTricWgK19pxbAYilxU/8wy1knQoxNT0Diop6tddWmw1EeErIJSnQ7wk68IJ8/GK/MagR7vtZV4K/WR5PI9PMkb6s5ibO68oWh/6yu1HIwcUKMmcn0n4ok9HxjNj1bNAPfOnpu76ZaQhYjNxcZO3c4LUUoJw2nG+nTXj/Nx0=~1',
        'ak_bmsc': 'FEEAF372936F9172E6606CC97DA188B9~000000000000000000000000000000~YAAQBuscuFhAeYmWAQAAuHUCzRvG8LIt9ajTBxt0zE19J70WDE0dylIIUf6wb1f9Flkdv0N7qlDJAkMoRLq52KfBfduE8Ni1TbLTOY1IzAJNSBEoGhxXzYXLSv5cgS+7ijvjn+AYd3wdwEXOvEpvoBiKv7zYHhT5x6+8qfqhEWhADDyihKoT23n7qSUQmJRmuAMtzdVlTz3M/SxOADf3oeMpFuqToayfo7jnlrHT2bkJbty1GyPEcLWxlIXiLibYh6z3r0EFmTXGrQZvxIdjFUl7ngdVN8pXM5iwTFDjW/QCvrtaHmZGPuYlicnCh7Yg9RDS35ND3Tv9QqdYpZnOTfXBjqt1GJAWCsFAp3x74+1w2BZaunCSr49pQwR2h3oV6A9LFpdmMLrRobflgEh6dffS7JZvXsp/jFASjN+/Tmpaj3feusxcj8U5Lvueoezf02tN/g3b7+Z8ko1v5FAUlZR2n6LZaR2JCzlcMLJ/dGDZMLAQTTmOFSOw7JDymoxcC+GH4Lx+1yl+aQK52mw=',
        'xpth': 'x-o-mart%2BB2C~x-o-mverified%2Bfalse',
        'walmart-identity-web-code-verifier': '1lrzs21N_RB2N4Nzxh5yYGSnY6TYAtrBDmft432EnDs',
        'TS012af430': '01bd4b091789db244427c89cedb4f76f2a6bc0bcd7969c09892fc45aedf4e9cc4bc494ae4d35afc48e98c140d6a20ad5e6dfb16717',
        'CID': 'f7b73c43-9694-4b60-a3d3-91d5e057f8a6',
        'SPID': '095d38579e1c150cce427c00a54ce55263a7f497b16681bd2236af5aa208f49cb7c7e78773640a0a9a91ff926a7899f6wmcxo',
        '_vc': '8DukAPDvBElPUA1ndyD3yjUbP6kRCrEkYH6kvqH+Tmo=',
        'customer': '%7B%22firstName%22%3A%22Graham%22%2C%22lastNameInitial%22%3A%22P%22%2C%22ceid%22%3A%22a7d8a75edf02acda253856b591c58f011ba0ce58c9579ab193779711d8dca5f4%22%7D',
        'hasCID': '1',
        'sod': 'torbit1736110930',
        'type': 'REGISTERED',
        'wm_accept_language': 'en-US',
        '_s': ':1747199627273',
        '_sc': '0whysKaWYotVyMQQa%2Fx9AI2Wnx7%2Bxrq7g4JDuaMf0xE%3D',
        '_tpl': '40',
        '_tplc': 'HlD7KYVKG4PTO82LqiU905L1C1pcLNi8oTS+P+cdWAQ=',
        'assortmentStoreId': '3545',
        'auth': 'MTAyOTYyMDE4urFYwSBXhZAP4stMhYb2zi2WvJVNUHe9U5Fhdtl0GT745XCUjaqNcfSENe7j4rJ3Eqv2mDGBh3sKpxN7pt8gFzreKh7yCzxu8zVUwgzKsi52faNy4xK57I8j8gR%2FH852oHOs%2FstByN418DB3KSmMoqHeJIIZwSRWhp%2FtFFuUQto2fOzjsshxQ%2B%2FS9m47DZDZPViMwlpOWNB25KlRJ4rBGmxVon1qX0ChQbDsykETs9gK0n9BhGlO4%2Bb3fjnSMvlIJeTBE0%2BIwRzF3a1YAFkV316X9rjR7En7Waqdcpv808il%2FV7%2BBnks9bBGU7LznJnw%2FUSNGYFoDt%2FK%2Fon0YCLnF%2FLaKRVU3o7h%2FsolApPyGTi37hEsWZhpDPUbTi%2F9uT01%2FE%2Fo0QyJw1sJpLas3GXr4F0kbXsix6RLvADsQrt834Dz6q38V8BD6evc5nJS%2F%2BEM',
        'exp-ck': '-MY-A1-lFRV10gV4j10pOsd13M4u723Og5Y13d8P619g0q61EK9aV3HSRYO1HdUaA1Hhu9n2KYwc81KmT311MOJkx1Nw8KH1NwgWC2QJ4Ah1QWs5E2T5-rl4UHbkG1UtF0i1YuWze2dNJU-6f-Htx1fdm-71hCVo02hQuxT1jCaA11kbPOQ1mYj1t1mayCK9pN4Kz1u7rEL1vAxr69xhGTF1yr7Cz3zOIfO1',
        'xptwj': 'uz:96d544c8835bd35fbbd4:lIZM3/L0KVh/iLC/fMQPnDclNVXx9RZFo+J838v32UDGGTuIKoDNe/fL+30S1V5/QcE+hJJAzYLnI0X8PjJfptR4VigLx8hw7+uyvzrd8mWn8lOk7q0b3zmHAwUzHG1OnZn91yG29UFbQ+lbnJiRy+6gFooJjUj2yr56+335SO7D0myGmMdWr7P0SVClQpVVYUxJNHR/hGRlBT9atPGMmM250/tfyyReDXVy',
        '_px3': '8ce3c429ee9ab8bcb9c9f2a4cc21dab2eb686a1a9474f2ee64e919ce28970cef:QuiOFL+f5aG1uwHAo2REtuoIAmdjCwMoy4fC6pQa+pqDJ+cfavozlnv8VD2atCdVn7VgoVRTYSccW5KOOMyRLg==:1000:Tnau/wq55WMfYQNpOax9HCRG2l9ep6NxBl5/XZaRtCgDe8FfDWqnJkWfO98RzhC6mpMrpmt5/e82UO478JNJKVsT0FsuU5RgtIZlcE6AbXZE9XDBRNSztuHJvsB87QjV63ZGFkljsVzFFF9jKENImBctewvXxiGHZaYcgOZwfHDgXGt7QfRWrVZIV1OwoxhUMVbu1wLSgog5w7nw5cga6xN+vugHQJ62AmrsSEuYV5Y=',
        '_astc': '42a6ae6a1cac89405b364d0336160533',
        'dimensionData': '738',
        'xptc': '_m%2B9~_s%2B:1747199627273~assortmentStoreId%2B3545',
        'xpa': '-5-yD|-MY-A|-lFRV|0gV4j|0pOsd|227cg|3M4u7|3Og5Y|3VCVY|3d8P6|5oeq_|68ylv|8Atw4|9LNAP|9NE0o|9g0q6|9wmku|AQjWd|AftpL|EK9aV|HSRYO|HdUaA|Hhu9n|KYwc8|KmT31|LKsvQ|LRSst|MOJkx|NeOaM|Nw8KH|NwgWC|QJ4Ah|QNY8m|QWs5E|SS6hg|T5-rl|UHbkG|UtF0i|VQvcl|YuWze|bM3bT|dNJU-|f-Htx|fdm-7|g7Tze|gPMf8|hCVo0|hQuxT|jCaA1|jM1ax|kbPOQ|mYj1t|mayCK|pN4Kz|u7rEL|vAxr6|xhGTF|y3j_2|yr7Cz|zOIfO|zR-nl',
        'com.wm.reflector': '"reflectorid:0000000000000000000000@lastupd:1747199633000@firstcreate:1746855634737"',
        'akavpau_p2': '1747200233~id=682bfa0ff0a331fbe34e5ca5b19bc3cf',
        '_lat': 'bd0629bc121e02b92eb2a89b8ba411aewmart',
        '_msit': '0fb34e22195216b3255a3f43dc2735d7wmart',
        'xpm': '1%2B1747199632%2BRK8oFWsrX2CNmeRZRsehxE~f7b73c43-9694-4b60-a3d3-91d5e057f8a6%2B0',
        'xptwg': '604273359:20F2E268283DB00:50FEA37:709324DB:2DB8B3F2:B4F907FD:',
        'TS012768cf': '01d80600846a1dc5fd4d5de83720c81a1b0061514136b1bd59c7dbe1000eddd3cea56e6b46566d1bf61aeaa2ffc8b311bb7d178b2f',
        'TS01a90220': '01d80600846a1dc5fd4d5de83720c81a1b0061514136b1bd59c7dbe1000eddd3cea56e6b46566d1bf61aeaa2ffc8b311bb7d178b2f',
        'TS2a5e0c5c027': '0899fb2d9dab2000f91459348f9e16d9b5a96f89af557b420eaada4b13fdb818c8cac051ecd48a3408634436921130002984f49bdde9c4eaabd4ffea1a9a785009170c202c95d55cd9f1aaa04e4db5b56426ec2314872b0666e69e8b769acb4b',
        'akavpau_p4': '1747200233~id=682bfa0ff0a331fbe34e5ca5b19bc3cf',
        'if_id': 'FMEZARSF/0yBMFlGGFLYrNUr5BZZbb1DErBcM8cj/0BXoHVZerY4wk+uJI+IoJVZSWv4lwKXY5DQdtcYKCbc9KoojIGgaRJpa8e9iY8XSmblVhR5XhDwCXG1bk9jzvBYOaBfyErb+NJxhm4ABRMhpoI809VWvL2Awhud1NIvgKmLSJ7cECLKbdJb4ngY70X25CY/+9wPiwwLCeHgGg7LkytpqBTD1FFjFetSUUOHBmnXuEwxIZlpxK6IY0VmItS11Cwpzsp0ynVCbn0+JHG1RTmsqqld16Nb4QYA6RV7YJ71CWuaHC/ozIY7UmYYcT0JRs5DNCf/w0u00NdXVSgwE8A3dtg=',
        'TS016ef4c8': '01a45e1c89311abbb1c364d1b4ebd69b6145f5ff39541aa0fa3b33452fcf2715c1e31b46752d1e9f079f71af8e820925bb652f7693',
        'TS01f89308': '01a45e1c89311abbb1c364d1b4ebd69b6145f5ff39541aa0fa3b33452fcf2715c1e31b46752d1e9f079f71af8e820925bb652f7693',
        'TS8cb5a80e027': '089bdf021fab20005de6b442ce07dd4542af14b14a11a62c6d6c1c66d4303a2e38cf10887ffffd81085d695f43113000e2e103409526ae7d8a4f8ad8fae506b683f2b7b50d5b7993f956f9c07cb8e8a54057c3e16a19374b8ec808bb5206bffe',
        '_pxde': 'a5a1adb37929c3ba3913ba23a7be3b9a219b4fe8dddb79591a700b9ffd21f3c0:eyJ0aW1lc3RhbXAiOjE3NDcxOTk2NDM5MzN9',
        }


        cookie_list = [{"name": k, "value": v} for k, v in cookies.items()]

        # import json
        # with open('walmart_cookies.json', 'w', encoding='utf-8') as f:
        #     json.dump(cookie_list, f, indent=4)

        return cookie_list

    except Exception as e:
        logger.error(f"Error getting cookies: {e}")
        return None

# print(json.dumps(get_cookies(), indent=4))