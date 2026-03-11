document.addEventListener("DOMContentLoaded", () => {
    if (window.location.pathname.startsWith("/api/")) {
        return;
    }

    function scheduleHourlyRefresh() {
        const now = new Date();
        const nextHour = new Date(now);
        nextHour.setMinutes(0, 5, 0);
        nextHour.setHours(now.getHours() + 1);

        const delay = Math.max(nextHour.getTime() - now.getTime(), 1000);
        window.setTimeout(() => {
            window.location.reload();
        }, delay);
    }

    scheduleHourlyRefresh();
});
