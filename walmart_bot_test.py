"""
Walmart Bot - Automates adding products to cart on Walmart's website.

This script provides functionality to add multiple products to a Walmart shopping cart
in parallel, with smart window positioning, error handling, and retry mechanisms.
"""

import os
import json
import time
import random
import logging
import traceback
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from seleniumbase import SB
from screeninfo import get_monitors
from utils.helpers import get_cookies
from logs.custom_logging import setup_logging

# Configure logging
logger = setup_logging(console_level=logging.DEBUG)


class WalmartBot:
    """
    A bot that automates adding products to Walmart shopping cart.
    
    Features:
    - Multi-threaded operation for parallel processing
    - Smart window positioning to avoid overlap
    - Captcha detection and handling
    - Automatic retries
    - Detailed logging
    - Result tracking and storage
    """
    
    def __init__(self, max_workers: int = 30, retry_attempts: int = 1):
        """
        Initialize the WalmartBot.
        
        Args:
            max_workers: Maximum number of concurrent worker threads
            retry_attempts: Number of times to retry adding a product to cart
        """
        self.logger = logger
        self.add_to_cart_button_xpath = './/div[contains(@data-testid, "add-to-cart-section")]//button[contains(@aria-label, "Add to cart")][1]'
        self.max_workers = max_workers
        self.retry_attempts = retry_attempts

        # Configure window positioning
        self._configure_window_settings()
        
        # Track used positions for window placement
        self.used_positions = set()

    def _configure_window_settings(self):
        """Configure the window settings based on the screen size."""
        try:
            self.monitor = get_monitors()[0]
            self.SCREEN_WIDTH = self.monitor.width
            self.SCREEN_HEIGHT = self.monitor.height - 80
        except Exception as e:
            # Fallback to default values if screen info can't be retrieved
            self.logger.warning(f"⚠️ Could not get monitor info: {e}. Using default values.")
            self.SCREEN_WIDTH = 1920
            self.SCREEN_HEIGHT = 1080 - 80
            
        # Set window dimensions
        self.WINDOW_WIDTH = 600
        self.WINDOW_HEIGHT = 400
        self.WINDOW_PADDING = 10  # Space between windows

    def get_smart_random_position(self, index: int) -> Tuple[int, int]:
        """
        Get a window position that avoids overlapping with other windows.
        
        Args:
            index: The index of the browser window
            
        Returns:
            A tuple of (x, y) coordinates for window placement
        """
        screen_height = self.SCREEN_HEIGHT - 80
        cols = max(1, self.SCREEN_WIDTH // (self.WINDOW_WIDTH + self.WINDOW_PADDING))
        rows = max(1, screen_height // (self.WINDOW_HEIGHT + self.WINDOW_PADDING))
        max_slots = cols * rows

        # Use grid positioning for first set of windows
        if index < max_slots:
            row = index // cols
            col = index % cols
            x = col * (self.WINDOW_WIDTH + self.WINDOW_PADDING)
            y = row * (self.WINDOW_HEIGHT + self.WINDOW_PADDING)
        else:
            # For additional windows, find a random position that's not already used
            for _ in range(50):  # Try up to 50 times to find an unused position
                x = random.randint(50, self.SCREEN_WIDTH - self.WINDOW_WIDTH - 50)
                y = random.randint(50, screen_height - self.WINDOW_HEIGHT - 50)
                
                # Check if position is sufficiently far from existing windows
                if all((abs(x - pos_x) > 50 or abs(y - pos_y) > 50) 
                       for pos_x, pos_y in self.used_positions):
                    break
            
        self.used_positions.add((x, y))
        return x, y
    
    def save_product_data(self, product: Dict[str, Any], is_success: bool):
        """
        Save product data to success or failure file.
        
        Args:
            product: Dictionary containing product information
            is_success: True if the product was added successfully, False otherwise
        """
        file_dir = 'data/output_data'
        os.makedirs(file_dir, exist_ok=True)

        # Decide filename based on success/failure
        file_name = 'added_to_carts_successful_products.json' if is_success else 'failed_to_add_products.json'
        file_path = os.path.join(file_dir, file_name)

        # Load existing data
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}

        # Update and save
        data.update(product)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def is_request_blocked(self, browser) -> bool:
        """
        Check if a request is blocked by a captcha or other form of protection.

        Args:
            browser: The SeleniumBase browser instance

        Returns:
            True if a captcha or other form of protection is detected, False otherwise
        """
        try:
            body = browser.get_text('body')

            # Check for captcha elements
            if (browser.is_element_visible('.//h1[contains(text(), "Robot or human?")]') or
                browser.is_element_visible('.//h2[contains(text(), "Robot or human?")]')):
                self.logger.warning("Captcha detected!")
                return True
            elif body and len(body) < 500 and 'Forbidden' in body:
                self.logger.warning("Forbidden access detected!")
                return True
            else:
                return False

        except Exception as e:
            self.logger.error(f"Error checking for captcha or other protection: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    def is_account_logged_in(self, browser) -> Tuple[Optional[bool], bool]:
        """
        Check if user is logged into Walmart account.

        Args:
            browser: The SeleniumBase browser instance

        Returns:
            Tuple of (is_logged_in, is_captcha_detected) where:
            - is_logged_in: True if logged in, False if not, None if can't determine
            - is_captcha_detected: True if captcha detected, False otherwise
        """
        try:
            a_tag_selector = './/a[@link-identifier="Account"]'
            inside_div_selector = './/div[@data-automation-id="headerSignIn"]'
            
            # If any of these elements are visible, we have logged in successfully
            if (browser.is_text_visible('Hi, ', a_tag_selector, by='xpath') or 
                browser.is_text_visible('Hi, ', inside_div_selector, by='xpath')):
                self.logger.debug("Logged in successfully!")
                return True, False
                
            elif (browser.is_text_visible('Sign In, ', a_tag_selector, by='xpath') or 
                browser.is_text_visible('Sign In, ', inside_div_selector, by='xpath')):
                self.logger.debug("Not logged in!")
                return False, False

            elif self.is_request_blocked(browser):
                self.logger.debug("Request blocked!")
                return False, True

            else:
                return True, None
            
        except Exception as e:
            self.logger.error(f"Error checking login status: {e}")
            self.logger.debug(traceback.format_exc())
            return None, None
    
    def is_add_to_cart_button_visible(self, browser) -> bool:
        """
        Check if the Add to Cart button is visible on the page.
        
        Args:
            browser: The SeleniumBase browser instance
            
        Returns:
            True if the button is visible, False otherwise
        """
        try:
            if browser.is_element_visible(self.add_to_cart_button_xpath):
                self.logger.info("Add to cart Button is visible!")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error checking Add to Cart button visibility: {e}")
            return False

    def is_item_added_to_cart(self, browser) -> bool:
        """
        Check if the item was successfully added to cart.
        
        Args:
            browser: The SeleniumBase browser instance
            
        Returns:
            True if the item appears to be added to cart, False otherwise
        """
        try:
            # Check if "Added to cart" message appears
            added_message_xpath = './/h1[contains(text(), "Added to cart!")]'
            
            # Check if View Cart button appears
            view_cart_xpath = './/button[contains(text(), "View cart")]'
            
            # If any of these elements are visible, item was likely added successfully
            if (browser.is_element_visible(added_message_xpath) or 
                browser.is_element_visible(view_cart_xpath)):
                return True
                
            return False
        except Exception as e:
            self.logger.error(f"Error checking if item was added to cart: {e}")
            return False
        
    def attempt_add_to_cart(self, product_info: Dict, category_key: str, window_index: int = 0) -> bool:
        """
        Attempt to add a product to cart.
        
        Args:
            product_info: Dictionary containing product information
            category_key: The product category key from the JSON file
            window_index: Index for window positioning
            
        Returns:
            True if product was successfully added to cart, False otherwise
        """
        product_url = product_info.get('url')
        product_name = product_info.get('name', 'Unknown Product')
        
        self.logger.info(f"Attempting to add to cart for '{category_key}' ")
        
        retries = 0
        proxy_needed = False
        
        while retries < self.retry_attempts:
            try:
                # Determine profile path
                if proxy_needed:
                    profile = r'D:\Web Scraping\Client Projects\Dereal\Project1 (Walmart Bot)\new source code\profiles\sb_with_proxy'
                else:
                    profile = r'D:\Web Scraping\Client Projects\Dereal\Project1 (Walmart Bot)\new source code\profiles\sb_without_proxy'

                with SB(
                        uc=True, 
                        user_data_dir=profile,
                        extension_dir="proxy_auth_plugin" if proxy_needed else None,
                        chromium_arg='--ignore-certificate-errors' if proxy_needed else None,
                        ) as browser:
                    
                    # Configure browser window
                    x, y = self.get_smart_random_position(window_index)

                    browser.set_window_size(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
                    browser.set_window_position(x, y)

                    browser.open(product_url)
                    # Add cookies and navigate to product page
                    cookie_list = get_cookies()
                    for cookie in cookie_list:
                        browser.add_cookie(cookie)

                    browser.sleep(2)
                    browser.refresh()
                    
                    # Wait for page to load
                    try:
                        browser.wait_for_element_visible(
                            './/body',
                            timeout=180 if proxy_needed else 40
                        )
                    except Exception as e:
                        self.logger.error(f"Error waiting for page to load: {e}")
                        self.logger.debug(traceback.format_exc())
                        retries += 1
                        self.logger.warning(f"Retrying '{category_key}'... {retries}/{self.retry_attempts}")
                        continue
                    
                    # Check login status and for captcha
                    is_logged_in, captcha_detected = self.is_account_logged_in(browser)
                    
                    if captcha_detected:
                        self.logger.warning("Captcha detected, switching to proxy")
                        retries += 1
                        proxy_needed = True
                        self.logger.warning(f"Retrying '{category_key}' with proxy... {retries}/{self.retry_attempts}")
                        continue
                    
                    if is_logged_in:
                        # Check for Add to Cart button
                        if self.is_add_to_cart_button_visible(browser):
                            try:
                                # Click Add to Cart button
                                button = browser.wait_for_element_visible(self.add_to_cart_button_xpath, timeout=30)
                                button.click()
                                time.sleep(4)  # Wait for cart update
                                
                                # Check if item was added to cart
                                if self.is_item_added_to_cart(browser):
                                    return True
                                else:
                                    self.logger.warning(f"Failed to add to cart item for: '{category_key}'")
                            except Exception as e:
                                self.logger.error(f"Error clicking Add to Cart button: {e}")
                        else:
                            already_added = self.is_item_added_to_cart(browser)
                            if already_added:
                                self.logger.info('Item already added to cart!, Skipping...')
                                return True
                            else:
                                self.logger.warning(f"Add to cart button not found for item: '{category_key}'")
                    else:
                        self.logger.warning("Not logged in to account")
                        
            except Exception as e:
                self.logger.error(f"Error in browser session: {e}")
                self.logger.debug(traceback.format_exc())
            
            retries += 1
            self.logger.warning(f"Retrying '{category_key}'... {retries}/{self.retry_attempts}")
        
        self.logger.error(f"❌ Failed to add to cart after {self.retry_attempts} attempts: '{category_key}'")
        return False
        
    def process_product(self, item_key: str, item_info: Dict[str, Any], window_index: int) -> Optional[Dict]:
        """
        Process a product category and attempt to add eligible products to cart.
        
        Args:
            item_key: The key for the product category
            item_info: Dictionary containing product category details and eligible products
            window_index: Index for window positioning
            
        Returns:
            Updated product data if successful, None otherwise
        """
        # Check if there are eligible products
        if not item_info.get('eligible_products') or not item_info['eligible_products'][0]:
            self.logger.error(f"No eligible products found for '{item_key}'")
            return None
            
        products_list = item_info['eligible_products'][0].copy()  # Make a copy to avoid modifying original

        # Try to add products to cart in order (cheapest first)
        for i, eligible_product in enumerate(products_list):
            # Skip products already added to cart
            if eligible_product.get('added_to_cart', False):
                self.logger.info(f"Skipping already added product: '{eligible_product['name']}'")
                continue
                
            # Try to add this product to cart
            if self.attempt_add_to_cart(eligible_product, item_key, window_index):
                self.logger.info(f"✅ Successfully added to cart: '{item_key}'")
                eligible_product['added_to_cart'] = True
                eligible_product['added_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                result = {item_key: item_info}
                return result
                
            # If this is the second product and we've failed twice, stop trying
            if i >= 1 and self.retry_attempts >= 2:
                self.logger.warning(f"Stopping after {i+1} products and {self.retry_attempts} retries each")
                break
            
        return None

    def add_to_cart_single_product(self, item_key: str, item_info: Dict[str, Any], window_index: int):
        """
        Process a single product category and save the results.
        
        Args:
            item_key: The key for the product category
            item_info: Dictionary containing product category details and eligible products
            window_index: Index for window positioning
        """
        # Add some randomness to avoid all threads starting at once
        time.sleep(random.uniform(1, 3))
        
        added_to_cart_product = self.process_product(item_key, item_info, window_index)
        if added_to_cart_product:
            self.logger.info(f"✅ Product '{item_key}' added successfully. Saving to success file...")
            self.save_product_data(added_to_cart_product, is_success=True)
        else:
            self.logger.warning(f"❌ Product '{item_key}' could not be added. Saving to failure file...")
            result = {item_key: item_info}
            self.save_product_data(result, is_success=False)

    def add_products_to_cart(self, products_data: Dict[str, Any]):
        """
        Add multiple products to cart in parallel.

        Args:
            products_data: Dictionary with product categories as keys and product information as values
        """
        # Reset used positions for window placement
        self.used_positions = set()
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(products_data))) as executor:
            futures = []
            for idx, (item_key, item_info) in enumerate(products_data.items()):
                futures.append(
                    executor.submit(self.add_to_cart_single_product, item_key, item_info, idx)
                )
            
            # Wait for all tasks to complete
            for future in futures:
                future.result()
        
        self.logger.info("✅ All product processing complete!")


def main():
    """
    Main function to run the WalmartBot.
    
    This function demonstrates how to use the WalmartBot class.
    """
    # Load product data from file
    try:
        with open('data/output_data/scraped_products.json', encoding='utf-8') as f:
            products_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
       logger.error(f'Failed to load data from file!: {e}')


    # Initialize and run bot
    bot = WalmartBot()
    bot.add_products_to_cart(products_data)


if __name__ == "__main__":
    main()