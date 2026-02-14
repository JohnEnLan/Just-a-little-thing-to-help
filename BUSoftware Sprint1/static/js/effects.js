document.addEventListener("DOMContentLoaded", () => {
    const rails = Array.from(document.querySelectorAll(".leaf-rail"));
    if (!rails.length) {
        return;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
    }

    const palettes = [
        ["#183b24", "#2e6a40"],
        ["#215c3c", "#4f8b63"],
        ["#3f7b58", "#79a882"],
        ["#5f8f68", "#a6c59b"],
    ];

    const states = rails.map((rail) => ({
        rail,
        stream: rail.querySelector("[data-leaf-stream]"),
        side: rail.classList.contains("leaf-rail--right") ? "right" : "left",
    }));

    function pickPalette() {
        return palettes[Math.floor(Math.random() * palettes.length)];
    }

    function decorateLeaf(leaf, config) {
        leaf.style.setProperty("--leaf-size", `${config.size}px`);
        leaf.style.setProperty("--leaf-scale", config.scale);
        leaf.style.setProperty("--leaf-drift", config.drift);
        leaf.style.setProperty("--leaf-duration", config.duration);
        leaf.style.setProperty("--leaf-rotation", config.rotation);
        leaf.style.setProperty("--leaf-start", config.startColor);
        leaf.style.setProperty("--leaf-end", config.endColor);
        leaf.style.left = `${config.left}px`;
    }

    function createLeafConfig(state, width) {
        const [startColor, endColor] = pickPalette();
        const direction = state.side === "left" ? 1 : -1;
        const size = 22 + Math.random() * 18;

        return {
            startColor,
            endColor,
            size,
            left: Math.random() * Math.max(width - size, 8),
            scale: (0.9 + Math.random() * 0.4).toFixed(2),
            drift: `${direction * (18 + Math.random() * 42)}px`,
            duration: `${4.8 + Math.random() * 2.8}s`,
            rotation: `${direction * (180 + Math.random() * 260)}deg`,
        };
    }

    function spawnLeaf(state) {
        const width = state.rail.getBoundingClientRect().width;
        if (width < 20 || !state.stream) {
            return;
        }

        const leaf = document.createElement("span");
        leaf.className = "leaf falling-leaf";
        decorateLeaf(leaf, createLeafConfig(state, width));
        leaf.addEventListener(
            "animationend",
            () => {
                leaf.remove();
            },
            { once: true }
        );
        state.stream.appendChild(leaf);
    }

    function scheduleStream(state) {
        window.setTimeout(() => {
            spawnLeaf(state);
            scheduleStream(state);
        }, 120 + Math.random() * 160);
    }

    states.forEach((state) => {
        scheduleStream(state);
        scheduleStream(state);
    });
});
