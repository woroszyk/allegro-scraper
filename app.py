from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import io
import os
from urllib.parse import urljoin, urlparse
import base64
import tempfile
import zipfile
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from io import BytesIO

app = Flask(__name__)

def get_image_info(img_url):
    try:
        response = requests.get(img_url, timeout=10, verify=False)
        response.raise_for_status()
        
        # Sprawdź typ MIME
        content_type = response.headers.get('content-type', '').lower()
        if not any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
            return None
            
        # Pobierz rozmiar
        size = len(response.content)
        
        # Otwórz obraz za pomocą PIL
        img = Image.open(BytesIO(response.content))
        format = img.format
        width, height = img.size
        
        return {
            'url': img_url,
            'format': format,
            'size': size,
            'width': width,
            'height': height
        }
    except (requests.RequestException, Image.UnidentifiedImageError, Exception) as e:
        print(f"Błąd podczas przetwarzania obrazu {img_url}: {str(e)}")
        return None

def process_images(url):
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Dodaj obsługę cookies dla Allegro
        if 'allegro.pl' in url:
            driver.get('https://allegro.pl')
            time.sleep(2)
            try:
                cookie_button = driver.find_element(By.ID, 'opbox-gdpr-consents-modal').find_element(By.XPATH, './/button[contains(text(), "akceptuję")]')
                cookie_button.click()
                time.sleep(1)
            except Exception as e:
                print(f"Nie udało się zaakceptować cookies: {str(e)}")
        
        # Ładujemy stronę
        driver.get(url)
        time.sleep(3)
        
        # Przewijamy stronę kilka razy
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        
        # Zbieramy wszystkie obrazy
        img_elements = driver.find_elements(By.TAG_NAME, 'img')
        img_urls = set()  # Używamy set() zamiast listy, aby uniknąć duplikatów
        
        def normalize_url(url):
            if not url or url.startswith('data:'):
                return None
            if not url.startswith(('http://', 'https://')):
                base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
                url = urljoin(base_url, url)
            return url.split('?')[0]  # Usuwamy parametry URL
        
        for img in img_elements:
            try:
                # Sprawdzamy różne atrybuty obrazu
                src = img.get_attribute('src')
                data_src = img.get_attribute('data-src')
                data_original = img.get_attribute('data-original')
                srcset = img.get_attribute('srcset')
                
                if src:
                    normalized_url = normalize_url(src)
                    if normalized_url:
                        img_urls.add(normalized_url)
                        
                if data_src:
                    normalized_url = normalize_url(data_src)
                    if normalized_url:
                        img_urls.add(normalized_url)
                        
                if data_original:
                    normalized_url = normalize_url(data_original)
                    if normalized_url:
                        img_urls.add(normalized_url)
                
                # Obsługa srcset
                if srcset:
                    for srcset_url in srcset.split(','):
                        parts = srcset_url.strip().split(' ')
                        if parts:
                            normalized_url = normalize_url(parts[0])
                            if normalized_url:
                                img_urls.add(normalized_url)
                        
            except Exception as e:
                print(f"Błąd podczas przetwarzania elementu img: {str(e)}")
                continue
    
    except Exception as e:
        print(f"Błąd podczas przetwarzania strony: {str(e)}")
        return []
        
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Błąd podczas zamykania przeglądarki: {str(e)}")
    
    # Przetwarzamy znalezione URL-e
    results = []
    for img_url in img_urls:
        try:
            result = get_image_info(img_url)
            if result:
                results.append(result)
        except Exception as e:
            print(f"Błąd podczas przetwarzania URL-a {img_url}: {str(e)}")
            continue
    
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        results = process_images(url)
        return jsonify({
            'images': results,
            'count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    try:
        images = request.json.get('images', [])
        format_type = request.json.get('format', 'original')
        
        if not images:
            return jsonify({'error': 'Nie wybrano żadnych obrazów'}), 400
            
        if len(images) == 1:
            # Pobieranie pojedynczego obrazu
            img_url = images[0]
            try:
                response = requests.get(img_url, timeout=10)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    output = BytesIO()
                    
                    if format_type == 'original':
                        # Zachowaj oryginalny format
                        img.save(output, format=img.format)
                        extension = img.format.lower()
                    else:
                        # Konwertuj do wybranego formatu
                        if img.mode in ('RGBA', 'LA'):
                            # Konwertuj obrazy z kanałem alpha do RGB
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'RGBA':
                                background.paste(img, mask=img.split()[3])
                            else:
                                background.paste(img, mask=img.split()[1])
                            img = background
                        else:
                            img = img.convert('RGB')
                        
                        if format_type.lower() == 'jpg':
                            extension = 'jpg'
                            img.save(output, format='JPEG', quality=95)
                        else:
                            extension = format_type.lower()
                            img.save(output, format=format_type.upper())
                        
                    output.seek(0)
                    return send_file(
                        output,
                        as_attachment=True,
                        download_name=f'obraz.{extension}',
                        mimetype=f'image/{extension}'
                    )
            except Exception as e:
                return jsonify({'error': f'Błąd podczas pobierania obrazu: {str(e)}'}), 500
        else:
            # Pobieranie wielu obrazów jako ZIP
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, 'obrazy.zip')
            
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                for i, img_url in enumerate(images):
                    try:
                        response = requests.get(img_url, timeout=10)
                        if response.status_code == 200:
                            img = Image.open(BytesIO(response.content))
                            img_output = BytesIO()
                            
                            if format_type == 'original':
                                # Zachowaj oryginalny format
                                img.save(img_output, format=img.format)
                                extension = img.format.lower()
                            else:
                                # Konwertuj do wybranego formatu
                                if img.mode in ('RGBA', 'LA'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    if img.mode == 'RGBA':
                                        background.paste(img, mask=img.split()[3])
                                    else:
                                        background.paste(img, mask=img.split()[1])
                                    img = background
                                else:
                                    img = img.convert('RGB')
                                
                                if format_type.lower() == 'jpg':
                                    extension = 'jpg'
                                    img.save(img_output, format='JPEG', quality=95)
                                else:
                                    extension = format_type.lower()
                                    img.save(img_output, format=format_type.upper())
                                
                            img_output.seek(0)
                            zip_file.writestr(f'obraz_{i+1}.{extension}', img_output.getvalue())
                    except Exception as e:
                        print(f"Błąd podczas przetwarzania obrazu {img_url}: {str(e)}")
                        continue
            
            return send_file(
                zip_path,
                as_attachment=True,
                download_name='obrazy.zip',
                mimetype='application/zip'
            )
    except Exception as e:
        return jsonify({'error': f'Błąd podczas przetwarzania: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
