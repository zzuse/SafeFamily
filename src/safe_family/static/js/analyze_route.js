// static/script.js
document.addEventListener("DOMContentLoaded", () => {
    const timeRangeEl = document.getElementById("timeRange");
    const customRangeEl = document.getElementById("customRange");

    timeRangeEl.addEventListener("change", () => {
        customRangeEl.style.display = (timeRangeEl.value === "custom") ? "block" : "none";
    });
});

async function runAnalysis() {
    const timeRange = document.getElementById("timeRange").value;
    const data = { time_range: timeRange };

    if (timeRange === "custom") {
        const startTime = document.getElementById("customStart").value;
        const endTime = document.getElementById("customEnd").value;

        if (!startTime || !endTime) {
            alert("Please fill in both start and end times!");
            return;
        }

        data.custom_start = startTime;  // e.g., "2025-11-10T01:30:00"
        data.custom_end = endTime;
    }

    try {
        const response = await fetch('/analyze', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const result = await response.json();
        document.getElementById("output").innerText = JSON.stringify(result, null, 2);
    } catch (err) {
        document.getElementById("output").innerText = `Error: ${err.message}`;
    }
}

document.getElementById("timeRange").addEventListener("change", function () {
    const customRange = document.getElementById("customRange");
    customRange.style.display = (this.value === "custom") ? "block" : "none";

    if (this.value === "custom") {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset()); // Fix timezone
        const nowStr = now.toISOString().slice(0, 19); // "2025-11-10T01:44:33"

        const endInput = document.getElementById("customEnd");
        if (!endInput.value) endInput.value = nowStr;

        const startInput = document.getElementById("customStart");
        if (!startInput.value) {
            const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
            startInput.value = oneHourAgo.toISOString().slice(0, 19);
        }
    }
});