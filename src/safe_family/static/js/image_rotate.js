document.addEventListener('DOMContentLoaded', function() {
    function applyRotation(img, rotation) {
        img.style.transform = `rotate(${rotation}deg)`;
        
        if (rotation % 180 !== 0) {
            const w = img.offsetWidth;
            const h = img.offsetHeight;
            const diff = Math.abs(w - h) / 2;
            img.style.margin = `${diff}px 0`;
        } else {
            img.style.margin = '0';
        }
    }

    const images = document.querySelectorAll('.rotatable-image');
    images.forEach(img => {
        const mediaId = img.dataset.mediaId;
        const savedRotation = localStorage.getItem(`rotation_${mediaId}`);
        if (savedRotation) {
            const rotation = parseInt(savedRotation);
            if (img.complete) {
                applyRotation(img, rotation);
            } else {
                img.addEventListener('load', () => applyRotation(img, rotation));
            }
        }
    });

    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.rotate-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            
            const mediaId = btn.dataset.mediaId;
            const img = document.querySelector(`.rotatable-image[data-media-id="${mediaId}"]`);
            if (!img) return;

            let currentRotation = 0;
            const transform = img.style.transform;
            if (transform && transform.includes('rotate')) {
                const match = transform.match(/rotate\((\d+)deg\)/);
                if (match) currentRotation = parseInt(match[1]) || 0;
            }
            
            let newRotation = (currentRotation + 90) % 360;
            applyRotation(img, newRotation);
            localStorage.setItem(`rotation_${mediaId}`, newRotation);
        }
    });
});
