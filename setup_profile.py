import os
import zipfile

def create_proxy_auth_extension_dir(proxy_host, proxy_port, proxy_username, proxy_password, dir_path="proxy_auth_plugin"):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    manifest_json = """{
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth Extension",
        "permissions": [
            "proxy", "tabs", "unlimitedStorage", "storage",
            "<all_urls>", "webRequest", "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }"""

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "https",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
            }},
            bypassList: ["localhost"]
        }}
    }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: "{proxy_username}",
                    password: "{proxy_password}"
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """

    with open(os.path.join(dir_path, "manifest.json"), "w") as f:
        f.write(manifest_json)
    with open(os.path.join(dir_path, "background.js"), "w") as f:
        f.write(background_js)


from seleniumbase import SB

# Proxy Sample "http://brd-customer-hl_62799e1a-zone-walmart_proxy-country-us:a3qg5vo43tb8@brd.superproxy.io:33335"
def selenium_base_test(url: str):
    create_proxy_auth_extension_dir(
        proxy_host="brd.superproxy.io",
        proxy_port="33335",
        proxy_username="brd-customer-hl_62799e1a-zone-walmart_proxy",
        proxy_password="a3qg5vo43tb8",
        dir_path="proxy_auth_plugin"
    )

    with SB(
        uc=True,
        user_data_dir=r'D:\Web Scraping\Client Projects\Dereal\Project1 (Walmart Bot)\new source code\my_profile',
        extension_dir="proxy_auth_plugin",  # ✅ Use unzipped folder here
        chromium_arg="--ignore-certificate-errors"
        
    ) as browser:
        browser.open(url)
        input() # Wait to see if IP actually changes or not


if __name__ == "__main__":
    # url = "http://httpbin.org/ip"
    url = "https://www.walmart.com/ip/Pre-Owned-Apple-iPhone-13-Mini-128GB-Fully-Unlocked-Blue-Refurbished-Good/1453355684"
    selenium_base_test(url)