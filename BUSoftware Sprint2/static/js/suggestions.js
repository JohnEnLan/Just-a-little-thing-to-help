document.addEventListener("DOMContentLoaded", () => {
    const feedbackRoot = document.getElementById("feedback-root");
    const suggestionList = document.getElementById("suggestion-list");
    const filePickers = Array.from(document.querySelectorAll("[data-file-picker]"));
    const sortToggle = document.querySelector("[data-sort-toggle]");
    const sortLinks = Array.from(document.querySelectorAll("[data-sort-link]"));
    const sortInput = document.querySelector('input[name="sort"]');
    const sortNoteLineOne = document.querySelector("[data-sort-note-line-one]");

    let currentSort =
        sortLinks.find((link) => link.classList.contains("is-active"))?.dataset.sortMode || "likes";

    filePickers.forEach((picker) => {
        const input = picker.querySelector(".file-picker__input");
        const nameNode = picker.querySelector("[data-file-name]");

        if (!input || !nameNode) {
            return;
        }

        input.addEventListener("change", () => {
            if (input.files && input.files.length > 0) {
                nameNode.textContent = input.files[0].name;
                return;
            }

            nameNode.textContent = "No file selected";
        });
    });

    if (!feedbackRoot || !suggestionList) {
        return;
    }

    function getSortNote(mode) {
        if (mode === "latest") {
            return "Sorted by newest submissions first.";
        }

        return "Sorted by likes first, then by newest submissions.";
    }

    function updateSortState(mode) {
        currentSort = mode;

        sortLinks.forEach((link) => {
            link.classList.toggle("is-active", link.dataset.sortMode === mode);
        });

        if (sortInput) {
            sortInput.value = mode;
        }

        if (sortNoteLineOne) {
            sortNoteLineOne.textContent = getSortNote(mode);
        }

        const nextUrl = new URL(window.location.href);
        if (mode === "likes") {
            nextUrl.searchParams.delete("sort");
        } else {
            nextUrl.searchParams.set("sort", mode);
        }
        window.history.replaceState({}, "", nextUrl);
    }

    function getCardLikeCount(card) {
        return Number(card.dataset.likeCountValue || 0);
    }

    function getCardCreatedTime(card) {
        const rawValue = card.dataset.createdAt || "";
        const parsed = Date.parse(rawValue);
        return Number.isNaN(parsed) ? 0 : parsed;
    }

    function compareCards(a, b, mode) {
        if (mode === "latest") {
            const createdDifference = getCardCreatedTime(b) - getCardCreatedTime(a);
            if (createdDifference !== 0) {
                return createdDifference;
            }

            return getCardLikeCount(b) - getCardLikeCount(a);
        }

        const likeDifference = getCardLikeCount(b) - getCardLikeCount(a);
        if (likeDifference !== 0) {
            return likeDifference;
        }

        return getCardCreatedTime(b) - getCardCreatedTime(a);
    }

    function applySort(mode) {
        const cards = Array.from(suggestionList.querySelectorAll("[data-suggestion-card]"));
        cards.sort((a, b) => compareCards(a, b, mode));
        cards.forEach((card) => suggestionList.appendChild(card));
        updateSortState(mode);
    }

    function setCardMessage(card, message, tone = "muted") {
        const messageNode = card.querySelector("[data-like-message]");
        if (!messageNode) {
            return;
        }

        messageNode.textContent = message;
        messageNode.dataset.tone = tone;
    }

    function updateLikeDisplay(card, likeCount) {
        card.dataset.likeCountValue = String(likeCount);

        const likeCountNode = card.querySelector("[data-like-count]");
        if (likeCountNode) {
            likeCountNode.textContent = `${likeCount} likes`;
        }
    }

    function markLiked(card) {
        const button = card.querySelector("[data-like-button]");
        const label = card.querySelector("[data-like-label]");

        if (button) {
            button.disabled = true;
            button.classList.add("is-liked");
        }

        if (label) {
            label.textContent = "Liked";
        }
    }

    function toggleCard(card) {
        const isExpanded = card.classList.toggle("is-expanded");
        card.setAttribute("aria-expanded", isExpanded ? "true" : "false");
    }

    async function handleLike(button) {
        const card = button.closest("[data-suggestion-card]");
        if (!card || button.disabled) {
            return;
        }

        const url = button.dataset.likeUrl;
        if (!url) {
            setCardMessage(card, "Like request is unavailable.", "error");
            return;
        }

        button.disabled = true;
        setCardMessage(card, "Saving your like...", "busy");

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                },
            });
            const payload = await response.json().catch(() => ({}));

            if (response.ok) {
                updateLikeDisplay(card, Number(payload.like_count || 0));
                markLiked(card);
                setCardMessage(card, "Thanks for supporting this suggestion.", "success");
                applySort(currentSort);
                return;
            }

            if (response.status === 409) {
                updateLikeDisplay(card, Number(payload.like_count || 0));
                markLiked(card);
                setCardMessage(
                    card,
                    payload.message || "You have already liked this suggestion.",
                    "warning"
                );
                applySort(currentSort);
                return;
            }

            button.disabled = false;
            setCardMessage(card, payload.error || "Unable to save your like right now.", "error");
        } catch (_error) {
            button.disabled = false;
            setCardMessage(card, "Unable to save your like right now.", "error");
        }
    }

    suggestionList.addEventListener("click", (event) => {
        const likeButton = event.target.closest("[data-like-button]");
        if (likeButton) {
            event.preventDefault();
            event.stopPropagation();
            handleLike(likeButton);
            return;
        }

        const card = event.target.closest("[data-suggestion-card]");
        if (card) {
            toggleCard(card);
        }
    });

    suggestionList.addEventListener("keydown", (event) => {
        if (event.target.closest("[data-like-button]")) {
            return;
        }

        const card = event.target.closest("[data-suggestion-card]");
        if (!card) {
            return;
        }

        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggleCard(card);
        }
    });

    if (sortToggle) {
        sortToggle.addEventListener("click", (event) => {
            const link = event.target.closest("[data-sort-link]");
            if (!link) {
                return;
            }

            event.preventDefault();

            const mode = link.dataset.sortMode || "likes";
            if (mode === currentSort) {
                return;
            }

            applySort(mode);
        });
    }
});
