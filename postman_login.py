from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate to Postman login
        page.goto("https://identity.getpostman.com/login")
        
        # Fill in the email and password
        page.fill('input[id="username"]', 'a7medbaz16@gmail.com')
        page.fill('input[id="password"]', 'jMXsne35urANvd04IrUUptD2wvAw8AGp')
        
        # Click the login button
        page.click('button[type="submit"]')
        
        # Wait for navigation
        page.wait_for_navigation()
        
        # Go to the Collections page
        page.goto('https://web.postman.co/workspace/My-Workspace~56378131-5637-43b3-8e2b-08b2c463c3c7/collection')
        
        # Close the browser
        # browser.close()

if __name__ == "__main__":
    run()