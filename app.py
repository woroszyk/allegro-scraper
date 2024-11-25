from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from PIL import Image
import io
import os
import subprocess
import platform
from urllib.parse import urljoin, urlparse
import base64
import tempfile
import zipfile
import time
import json
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from io import BytesIO
import threading
import queue
import random

app = Flask(__name__)

# Słownik do przechowywania postępu dla każdej sesji
progress_data = {}

def update_progress(session_id, status, progress, message):
    progress_data[session_id] = {
        'status': status,
        'progress': progress,
        'message': message
    }

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

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Dodaj nagłówki użytkownika
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
    chrome_options.add_argument('--lang=pl-PL')
    
    # Dodaj dodatkowe nagłówki
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Usuń webdriver info
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("Chrome został zainicjalizowany pomyślnie")
        return driver
    except Exception as e:
        print(f"Błąd podczas inicjalizacji Chrome: {str(e)}")
        if os.getenv('RENDER'):
            try:
                print("\nInformacje o systemie:")
                print(subprocess.check_output(['uname', '-a']).decode())
                
                print("\nZawartość katalogu domowego:")
                print(subprocess.check_output(['ls', '-la', os.path.expanduser('~')]).decode())
                
                print("\nZmienne środowiskowe:")
                print(subprocess.check_output(['env']).decode())
            except Exception as debug_e:
                print(f"Błąd podczas zbierania informacji diagnostycznych: {str(debug_e)}")
        raise

def process_images(url, session_id):
    update_progress(session_id, 'starting', 0, 'Inicjalizacja przeglądarki...')
    driver = get_driver()
    try:
        # Dodaj obsługę cookies dla Allegro
        if 'allegro.pl' in url:
            update_progress(session_id, 'cookies', 10, 'Akceptowanie cookies Allegro...')
            driver.get('https://allegro.pl')
            time.sleep(2)
            
            # Sprawdź czy jest captcha
            try:
                captcha_iframe = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'captcha')]"))
                )
                if captcha_iframe:
                    error_message = "Wykryto captcha. Spróbuj ponownie za kilka minut."
                    update_progress(session_id, 'error', 100, error_message)
                    return []
            except:
                pass  # Brak captcha, kontynuuj
                
            try:
                # Nowa metoda akceptacji cookies
                cookie_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(@data-role, 'accept-consent')]"))
                )
                cookie_button.click()
                time.sleep(1)
            except Exception as e:
                print(f"Nie udało się zaakceptować cookies: {str(e)}")
                try:
                    cookie_button = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'akceptuję')]"))
                    )
                    cookie_button.click()
                    time.sleep(1)
                except Exception as e2:
                    print(f"Nie udało się zaakceptować cookies alternatywną metodą: {str(e2)}")
        
        # Ładujemy stronę
        update_progress(session_id, 'loading', 20, 'Ładowanie strony...')
        print(f"Ładowanie strony: {url}")
        
        # Dodaj losowe opóźnienie
        time.sleep(random.uniform(2, 4))
        driver.get(url)
        
        # Sprawdź czy jest captcha na stronie produktu
        try:
            captcha_iframe = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'captcha')]"))
            )
            if captcha_iframe:
                error_message = "Wykryto captcha. Spróbuj ponownie za kilka minut."
                update_progress(session_id, 'error', 100, error_message)
                return []
        except:
            pass  # Brak captcha, kontynuuj
        
        # Czekamy na załadowanie głównych elementów
        update_progress(session_id, 'waiting', 30, 'Czekanie na załadowanie elementów strony...')
        
        # Czekaj na konkretne selektory Allegro
        if 'allegro.pl' in url:
            try:
                # Czekaj na galerię obrazów
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-box-name='Gallery']"))
                )
                # Czekaj na główny obraz
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-role='gallery-viewer']"))
                )
            except TimeoutException:
                print("Timeout podczas oczekiwania na elementy Allegro")
        else:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "img"))
                )
            except TimeoutException:
                print("Timeout podczas oczekiwania na obrazy")
        
        # Dodatkowe oczekiwanie na dynamiczne elementy
        time.sleep(random.uniform(3, 5))
        
        # Przewijamy stronę
        update_progress(session_id, 'scrolling', 40, 'Przewijanie strony w poszukiwaniu obrazów...')
        print("Przewijanie strony...")
        
        # Przewijanie z większą liczbą powtórzeń i losowymi przerwami
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1.5, 2.5))
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(random.uniform(1, 2))
        
        # Zbieramy obrazy z różnych selektorów
        update_progress(session_id, 'collecting', 50, 'Zbieranie elementów obrazów...')
        print("Zbieranie obrazów...")
        
        img_elements = []
        
        if 'allegro.pl' in url:
            # Specjalne selektory dla Allegro
            img_elements.extend(driver.find_elements(By.CSS_SELECTOR, "[data-role='gallery-viewer'] img"))
            img_elements.extend(driver.find_elements(By.CSS_SELECTOR, "[data-box-name='Gallery'] img"))
            img_elements.extend(driver.find_elements(By.CSS_SELECTOR, "[data-role='gallery-viewer-image']"))
        
        # Standardowe obrazy
        img_elements.extend(driver.find_elements(By.TAG_NAME, 'img'))
        
        # Obrazy w tle
        background_elements = driver.find_elements(By.XPATH, "//*[contains(@style, 'background-image')]")
        
        # Szukamy obrazów w różnych atrybutach
        data_img_elements = driver.find_elements(By.XPATH, "//*[@data-src or @data-lazy or @data-original or @data-image]")
        
        total_elements = len(img_elements) + len(background_elements) + len(data_img_elements)
        print(f"Znaleziono {total_elements} potencjalnych elementów z obrazami")
        
        img_urls = set()
        
        def extract_url_from_style(style):
            if not style:
                return None
            import re
            match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
            if match:
                return match.group(1)
            return None
            
        def normalize_url(url):
            if not url or url.startswith('data:'):
                return None
            if not url.startswith(('http://', 'https://')):
                try:
                    base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(driver.current_url))
                    url = urljoin(base_url, url)
                except Exception as e:
                    print(f"Błąd podczas normalizacji URL: {str(e)}")
                    return None
            return url.split('?')[0]

        update_progress(session_id, 'processing', 60, f'Przetwarzanie {total_elements} znalezionych elementów...')
        
        # Przetwarzanie standardowych obrazów
        for img in img_elements:
            try:
                for attr in ['src', 'data-src', 'data-lazy', 'data-original']:
                    url = img.get_attribute(attr)
                    if url:
                        normalized_url = normalize_url(url)
                        if normalized_url:
                            img_urls.add(normalized_url)
                
                srcset = img.get_attribute('srcset')
                if srcset:
                    for srcset_url in srcset.split(','):
                        parts = srcset_url.strip().split(' ')
                        if parts:
                            normalized_url = normalize_url(parts[0])
                            if normalized_url:
                                img_urls.add(normalized_url)
            except Exception as e:
                print(f"Błąd podczas przetwarzania elementu img: {str(e)}")
                
        # Przetwarzanie obrazów w tle
        for elem in background_elements:
            try:
                style = elem.get_attribute('style')
                url = extract_url_from_style(style)
                if url:
                    normalized_url = normalize_url(url)
                    if normalized_url:
                        img_urls.add(normalized_url)
            except Exception as e:
                print(f"Błąd podczas przetwarzania elementu tła: {str(e)}")
                
        # Przetwarzanie elementów z data-atrybutami
        for elem in data_img_elements:
            try:
                for attr in ['data-src', 'data-lazy', 'data-original', 'data-image']:
                    url = elem.get_attribute(attr)
                    if url:
                        normalized_url = normalize_url(url)
                        if normalized_url:
                            img_urls.add(normalized_url)
            except Exception as e:
                print(f"Błąd podczas przetwarzania elementu data: {str(e)}")

        print(f"Znaleziono {len(img_urls)} unikalnych URL-i obrazów")
        
        # Pobieranie i analiza obrazów
        results = []
        total_urls = len(img_urls)
        update_progress(session_id, 'downloading', 75, f'Pobieranie i analiza {total_urls} unikalnych obrazów...')
        
        for i, img_url in enumerate(img_urls):
            progress = 75 + (i / total_urls * 20)  # Od 75% do 95%
            update_progress(session_id, 'downloading', progress, f'Pobieranie i analiza obrazu {i+1} z {total_urls}...')
            
            try:
                result = get_image_info(img_url)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"Błąd podczas przetwarzania URL-a {img_url}: {str(e)}")
                continue

        update_progress(session_id, 'finishing', 95, 'Finalizacja wyników...')
        print(f"Pomyślnie przetworzono {len(results)} obrazów")
        
        # Końcowy status
        update_progress(session_id, 'completed', 100, f'Zakończono! Znaleziono {len(results)} obrazów.')
        return results
        
    except Exception as e:
        error_message = f"Błąd podczas przetwarzania strony: {str(e)}"
        update_progress(session_id, 'error', 100, error_message)
        print(error_message)
        return []
        
    finally:
        try:
            driver.quit()
        except Exception as e:
            print(f"Błąd podczas zamykania przeglądarki: {str(e)}")

@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Generuj unikalny identyfikator sesji
    session_id = str(time.time())
    
    try:
        # Uruchom proces analizy
        results = process_images(url, session_id)
        
        # Poczekaj na zakończenie przetwarzania
        time.sleep(1)  # Daj czas na ostatnią aktualizację statusu
        
        if not results:
            error_message = "Nie udało się przetworzyć strony"
            update_progress(session_id, 'error', 100, error_message)
            return jsonify({'error': error_message}), 500
        
        return jsonify({
            'session_id': session_id,
            'images': results,
            'count': len(results),
            'status': 'completed'
        })
    except Exception as e:
        error_message = str(e)
        update_progress(session_id, 'error', 100, f'Błąd: {error_message}')
        return jsonify({
            'session_id': session_id,
            'error': error_message,
            'status': 'error'
        }), 500

@app.route('/progress/<session_id>')
def get_progress(session_id):
    progress_info = progress_data.get(session_id, {
        'status': 'unknown',
        'progress': 0,
        'message': 'Brak danych o postępie'
    })
    return jsonify(progress_info)

@app.route('/')
def index():
    return render_template('index.html')

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
