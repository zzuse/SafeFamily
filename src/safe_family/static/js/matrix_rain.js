document.addEventListener('DOMContentLoaded', () => {
    const canvases = document.querySelectorAll('.matrix-canvas');
    // Exit if no canvases found
    if (canvases.length === 0) return;

    const chars = '0123456789ABCDEF@#$%^&*()_+-=[]{}|;:,.<>?';
    
    canvases.forEach(canvas => {
        const ctx = canvas.getContext('2d');
        let width, height, columns, drops;
        const fontSize = 14;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            width = canvas.width = parent.offsetWidth;
            height = canvas.height = parent.offsetHeight;
            columns = Math.ceil(width / fontSize);
            drops = new Array(columns).fill(1);
        };

        resize();
        
        // Resize observer handles dynamic layout changes
        if (canvas.parentElement) {
            new ResizeObserver(resize).observe(canvas.parentElement);
        }

        const draw = () => {
            // Semi-transparent fill to create trail effect
            // Using the card background color (#172a45) with low opacity
            ctx.fillStyle = 'rgba(23, 42, 69, 0.1)'; 
            ctx.fillRect(0, 0, width, height);

            ctx.fillStyle = '#64ffda'; // Matrix green/cyan text color
            ctx.font = fontSize + 'px monospace';

            for (let i = 0; i < drops.length; i++) {
                const text = chars[Math.floor(Math.random() * chars.length)];
                ctx.fillText(text, i * fontSize, drops[i] * fontSize);

                if (drops[i] * fontSize > height && Math.random() > 0.975) {
                    drops[i] = 0;
                }
                drops[i]++;
            }
        };

        // Run animation at ~20fps
        setInterval(draw, 50);
    });
});
