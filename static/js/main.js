document.addEventListener('DOMContentLoaded', function() {
    const urlInput = document.getElementById('urlInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const loader = document.getElementById('loader');
    const results = document.getElementById('results');
    const imageGallery = document.getElementById('imageGallery');
    const errorDiv = document.getElementById('error');
    const downloadSelected = document.getElementById('downloadSelected');
    const formatSelect = document.getElementById('formatSelect');
    const resolutionSort = document.getElementById('resolutionSort');

    analyzeBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) {
            showError('Proszę wprowadzić adres URL');
            return;
        }

        try {
            showLoader();
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url }),
            });

            const data = await response.json();
            if (response.ok) {
                displayResults(data.images);
            } else {
                showError(data.error || 'Wystąpił błąd podczas analizy strony');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Wystąpił błąd podczas komunikacji z serwerem');
        } finally {
            hideLoader();
        }
    });

    function showLoader() {
        loader.classList.remove('d-none');
        results.classList.add('d-none');
        errorDiv.classList.add('d-none');
    }

    function hideLoader() {
        loader.classList.add('d-none');
    }

    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.classList.remove('d-none');
        results.classList.add('d-none');
    }

    function displayResults(images) {
        imageGallery.innerHTML = '';
        if (images.length === 0) {
            showError('Nie znaleziono żadnych obrazów na stronie');
            return;
        }

        // Usuń duplikaty na podstawie URL
        const uniqueImages = images.filter((image, index, self) =>
            index === self.findIndex((t) => t.url === image.url)
        );

        // Sortowanie według wymiarów
        resolutionSort.addEventListener('change', () => {
            const sortValue = resolutionSort.value;
            if (sortValue === 'asc') {
                uniqueImages.sort((a, b) => (a.width * a.height) - (b.width * b.height));
            } else if (sortValue === 'desc') {
                uniqueImages.sort((a, b) => (b.width * b.height) - (a.width * a.height));
            }
            renderImages(uniqueImages);
        });

        const countInfo = document.createElement('div');
        countInfo.className = 'alert alert-info mb-4';
        countInfo.textContent = `Znaleziono ${uniqueImages.length} ${uniqueImages.length === 1 ? 'obraz' : uniqueImages.length < 5 ? 'obrazy' : 'obrazów'}`;
        imageGallery.parentElement.insertBefore(countInfo, imageGallery);

        renderImages(uniqueImages);
        results.classList.remove('d-none');
    }

    function renderImages(images) {
        imageGallery.innerHTML = '';
        images.forEach((image, index) => {
            const col = document.createElement('div');
            col.className = 'col-12 col-sm-6 col-md-4 col-lg-3 mb-4';
            
            const card = document.createElement('div');
            card.className = 'card h-100';
            
            const imageContainer = document.createElement('div');
            imageContainer.className = 'position-relative';
            
            const img = document.createElement('img');
            img.src = image.url;
            img.className = 'card-img-top';
            img.alt = `Obraz ${index + 1}`;
            img.style.maxHeight = '200px';
            img.style.objectFit = 'cover';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'form-check-input position-absolute m-2';
            checkbox.style.top = '0';
            checkbox.style.right = '0';
            checkbox.dataset.url = image.url;
            
            const cardBody = document.createElement('div');
            cardBody.className = 'card-body';
            cardBody.innerHTML = `
                <p class="card-text">
                    <small class="text-muted">
                        <strong>Format:</strong> ${image.format || 'Nieznany'}<br>
                        <strong>Rozmiar:</strong> ${formatSize(image.size || 0)}<br>
                        <strong>Wymiary:</strong> ${image.width || '?'}x${image.height || '?'}
                    </small>
                </p>
            `;
            
            imageContainer.appendChild(img);
            imageContainer.appendChild(checkbox);
            card.appendChild(imageContainer);
            card.appendChild(cardBody);
            col.appendChild(card);
            imageGallery.appendChild(col);
        });
    }

    function formatSize(bytes) {
        const sizes = ['B', 'KB', 'MB', 'GB'];
        if (bytes === 0) return '0 B';
        const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)));
        return Math.round(bytes / Math.pow(1024, i), 2) + ' ' + sizes[i];
    }

    downloadSelected.addEventListener('click', async () => {
        const selectedImages = Array.from(document.querySelectorAll('.form-check-input:checked'))
            .map(checkbox => checkbox.dataset.url);
        
        if (selectedImages.length === 0) {
            showError('Proszę wybrać obrazy do pobrania');
            return;
        }

        try {
            const format = formatSelect.value;
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    images: selectedImages,
                    format: format
                }),
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = selectedImages.length === 1 ? `obraz.${format === 'original' ? 'jpg' : format}` : 'obrazy.zip';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                const error = await response.json();
                showError(error.error || 'Wystąpił błąd podczas pobierania obrazów');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Wystąpił błąd podczas pobierania obrazów');
        }
    });
});
