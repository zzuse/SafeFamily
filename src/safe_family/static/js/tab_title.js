document.addEventListener('DOMContentLoaded', () => {
    let originalTitle = document.title;
    const funnyTitles = [
        "👀 I miss you...",
        "💔 Don't leave me!",
        "👻 Come back!",
        "🤖 Where are you?",
        "💊 Take your pill..."
    ];

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            // Store the title just in case it changed dynamically
            originalTitle = document.title;
            // Pick a random funny title
            const randomTitle = funnyTitles[Math.floor(Math.random() * funnyTitles.length)];
            document.title = randomTitle;
        } else {
            // Restore the original title
            document.title = originalTitle;
        }
    });
});
