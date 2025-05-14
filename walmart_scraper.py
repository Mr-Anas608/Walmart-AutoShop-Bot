from utils.helpers import HtmlPageScraper, HtmlParser
from logs.custom_logging import setup_logging
import logging
import asyncio
import traceback
import json
from typing import List, Dict, Optional, Any
import random

logger = setup_logging(console_level=logging.DEBUG)

class MyFastScraper:
    def __init__(self, input_items_info: List[Dict[str, Any]], batch_size: int = 100):
        """
        Initialize the scraper with input items and configuration.
        
        Args:
            input_items_info: List of product dictionaries with product_name, min_price, max_price
            batch_size: Number of items to process in each batch
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.html_page_scraper = HtmlPageScraper()
        self.html_parser = HtmlParser()
        self.input_items_info = input_items_info
        self.logger = logger
        self.batch_size = batch_size
        
    async def scrape_products(self, query: str) -> List[Dict[str, Any]]:
        """
        Scrape product information for a given search query.
        
        Args:
            query: Search term to look for
            
        Returns:
            List of parsed product dictionaries
        """
        try:
            # Create tasks for fetching multiple pages
            tasks = []
            for page in range(1, 3):  # Fetch first 2 pages
                params = {
                    "q": query,
                    "page": page,
                }
                tasks.append(self.html_page_scraper.request_html(params))
                
            # Wait for all page HTML content to be fetched
            html_contents = await asyncio.gather(*tasks)
            
            # Filter out None values (failed requests)
            valid_html_contents = [html for html in html_contents if html]
            
            if not valid_html_contents:
                self.logger.error(f"⚠️ No valid HTML content found for query: {query}")
                return []
                
            # Parse the HTML content to extract product information
            raw_parsed_products = self.html_parser.search_page_parser(valid_html_contents, query)
            self.logger.info(f"✅ Found {len(raw_parsed_products)} products for query: '{query}'")
            
            return raw_parsed_products
            
        except Exception as e:
            self.logger.error(f"❌ Error during scrape_products for {query}: {e}")
            self.logger.debug(traceback.format_exc())
            return []
    
    def process_product(self, item_info: Dict[str, Any], parsed_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process and filter products based on price range.
        
        Args:
            item_info: Dictionary containing product info with min_price and max_price
            parsed_products: List of products to filter and process
            
        Returns:
            Updated item_info dictionary with eligible_products added
        """
        try:
            product_name = item_info.get("product_name")
            
            # Convert to float to ensure proper comparison
            min_price = float(item_info.get("min_price", 0))
            max_price = float(item_info.get("max_price", float('inf')))
            
            # Filter products that fall within the price range
            filtered_products = []
            for product in parsed_products:
                try:
                    product_price = float(product.get("price", 0))
                    if min_price <= product_price <= max_price:
                        filtered_products.append(product)
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"⚠️ Invalid price format for product: {product.get('name', 'Unknown')}")
                    continue
            
            # Sort by price closest to min_price (presumably looking for best deals)
            if filtered_products:
                sorted_products = sorted(
                    filtered_products,
                    key=lambda x: abs(float(x.get("price", 0)) - min_price)
                )

                # Take top 2 matches, 2nd for backup
                 
                item_info["eligible_products"] = sorted_products[:2],

            else:
                self.logger.warning(f"⚠️ No eligible products found for {product_name}")
                item_info["eligible_products"] = [],
            
            return item_info
            
        except Exception as e:
            self.logger.error(f"❌ Error processing products for {item_info.get('product_name')}: {e}")
            self.logger.debug(traceback.format_exc())
            # Return the original item info but with empty eligible products
            item_info["eligible_products"] = []
            item_info["error"] = str(e)
            return item_info
    
    async def get_eligible_products(self) -> List[Dict[str, Any]]:
        """
        Main method to scrape and process all input products.
        
        Returns:
            List of input items with eligible products attached
        """
        try:
            # Process items in batches to avoid overwhelming the server
            results = []
            
            # Process in batches
            for i in range(0, len(self.input_items_info), self.batch_size):
                batch = self.input_items_info[i:i+self.batch_size]
                self.logger.info(f"Processing batch {i//self.batch_size + 1} ({len(batch)} items)")
                
                # Create scraping tasks for all items in this batch
                scrape_tasks = []
                for input_item_info in batch:
                    query = input_item_info.get("product_name")
                    scrape_tasks.append(self.scrape_products(query))
                
                # Execute all scraping tasks concurrently
                scraped_products = await asyncio.gather(*scrape_tasks)
                
                # Process products for each item in the batch
                for idx, input_item_info in enumerate(batch):
                    # Process each product with its corresponding scraped data
                    processed_item = self.process_product(input_item_info, scraped_products[idx])
                    results.append(processed_item)
                
                # Pause briefly between batches to avoid overloading the server
                if i + self.batch_size < len(self.input_items_info):
                    await asyncio.sleep(random.randint(1, 3))  # Random sleep between 1 to 3 seconds
            
            self.logger.info(f"✅ Successfully processed {len(results)} items")
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error in get_eligible_products: {e}")
            self.logger.debug(traceback.format_exc())
            return []

if __name__ == "__main__":
    from utils.helpers import load_input_data, save_output_data
    

    # Load input data
    input_items = load_input_data()
    
    # Create scraper instance (using only the first 5 items for testing)
    scraper = MyFastScraper(input_items[:2])
    
    # Run the scraper
    results = asyncio.run(scraper.get_eligible_products())

    save_output_data(results)