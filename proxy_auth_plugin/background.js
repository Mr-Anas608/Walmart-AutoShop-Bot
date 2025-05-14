
    var config = {
        mode: "fixed_servers",
        rules: {
            singleProxy: {
                scheme: "https",
                host: "brd.superproxy.io",
                port: parseInt(33335)
            },
            bypassList: ["localhost"]
        }
    };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {
            return {
                authCredentials: {
                    username: "brd-customer-hl_62799e1a-zone-walmart_proxy",
                    password: "a3qg5vo43tb8"
                }
            };
        },
        {urls: ["<all_urls>"]},
        ['blocking']
    );
    