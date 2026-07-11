const element = document.getElementById("bridge-element");
const selected_user_row_id = element.dataset.value; // Access data-value
const selected_user_name = element.dataset.user;
const selected_user_role = element.dataset.role;

const todoForm = document.getElementById("todoForm");
if (todoForm) {
    todoForm.addEventListener("submit", function (e) {
        const inputs = document.querySelectorAll(".task-input");
        const pattern = /^([^\[\]/]+\[[^\[\]]+\])$/; // matches: main[sub]
        for (const input of inputs) {
            if (input.value.trim() !== "" && !pattern.test(input.value.trim())) {
                e.preventDefault();
                alert(`❌ Invalid format: "${input.value}". Use "main task[sub task]" format.`);
                input.focus();
                return;
            }
        }
    });
}

document.querySelectorAll('.complete-checkbox').forEach(cb => {
    cb.addEventListener('change', function () {
        // Here will find data-task-id field in todo HTML
        const taskId = this.dataset.taskId;
        const completed = this.checked;
        const row = this.closest(".todo-row");
        const status = row ? (row.dataset.status || "").trim() : "";
        const timeSlot = row ? row.dataset.timeSlot : "";
        const endTime = parseSlotEndTime(timeSlot);
        if (status || (endTime && new Date() >= endTime && completed === false)) {
            this.checked = true;
            return;
        }

        fetch("/todo/mark_done", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                id: taskId,
                completed: completed
            })
        })
            .then(async r => {
                let data = null;

                // Check if response is JSON
                const text = await r.text();
                try {
                    data = JSON.parse(text);
                } catch (e) {
                    console.error("Server did not return JSON:", text);
                    throw new Error("Invalid JSON response");
                }
                return data;
            })
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert("Update failed!");
                }
            })
            .catch(err => {
                console.error("AJAX error:", err);
                alert("Error updating task");
            });
    });
});

function parseSlotEndTime(timeSlot) {
    if (!timeSlot) return null;
    const parts = timeSlot.split("-");
    if (parts.length < 2) return null;
    const end = parts[1].trim();
    const [hours, minutes] = end.split(":").map(Number);
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
    const endTime = new Date();
    endTime.setHours(hours, minutes, 0, 0);
    return endTime;
}

function parseSlotStartTime(timeSlot) {
    if (!timeSlot) return null;
    const parts = timeSlot.split("-");
    if (parts.length < 2) return null;
    const start = parts[0].trim();
    const [hours, minutes] = start.split(":").map(Number);
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
    const startTime = new Date();
    startTime.setHours(hours, minutes, 0, 0);
    return startTime;
}

function updateSlotProgress() {
    const now = new Date();
    document.querySelectorAll(".todo-row").forEach(row => {
        const timeSlot = row.dataset.timeSlot;
        const startTime = parseSlotStartTime(timeSlot);
        const endTime = parseSlotEndTime(timeSlot);
        if (!startTime || !endTime) return;

        const total = endTime - startTime;
        if (total <= 0) return;

        let progress = (now - startTime) / total;
        if (progress < 0) progress = 0;
        if (progress > 1) progress = 1;
        row.dataset.slotProgress = progress.toFixed(3);

        const checkbox = row.querySelector(".complete-checkbox");
        const status = (row.dataset.status || "").trim();
        const completed = row.dataset.completed === "true";
        const taskInput = row.querySelector(`input[name="task_${row.dataset.todoId}"]`);
        const isActive = now >= startTime && now < endTime && !completed;
        row.classList.toggle("is-active", isActive);
        if (now >= endTime) {
            if (checkbox) {
                checkbox.checked = true;
                checkbox.disabled = true;
            }
            if (!completed) {
                fetch("/todo/mark_done", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id: row.dataset.todoId, completed: true })
                })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            row.dataset.completed = "true";
                            if (taskInput) {
                                taskInput.classList.add("done");
                            }
                        }
                    })
                    .catch(err => console.error("Auto-complete error:", err));
            }
        } else if (checkbox && !status) {
            checkbox.disabled = false;
        }
        if (checkbox && status) {
            checkbox.disabled = true;
        }
    });
}

function updateNowLine() {
    const nowLine = document.getElementById("sf-rainbow-now");
    if (!nowLine) return;

    const rangeStart = nowLine.dataset.rangeStart;
    const rangeEnd = nowLine.dataset.rangeEnd;
    const startTime = parseSlotStartTime(`${rangeStart} - ${rangeEnd}`);
    const endTime = parseSlotEndTime(`${rangeStart} - ${rangeEnd}`);
    const now = new Date();

    if (!startTime || !endTime || endTime <= startTime || now < startTime || now > endTime) {
        nowLine.hidden = true;
        return;
    }

    const pct = ((now - startTime) / (endTime - startTime)) * 100;
    nowLine.style.left = `${pct}%`;
    nowLine.hidden = false;
}

function updateNextMissionEta() {
    const missionEl = document.getElementById("sf-next-mission");
    const etaEl = document.getElementById("sf-next-mission-eta");
    if (!missionEl || !etaEl) return;

    const startTime = parseSlotStartTime(`${missionEl.dataset.start} - 00:00`);
    if (!startTime) return;

    const diffMin = Math.round((startTime - new Date()) / 60000);
    etaEl.textContent = diffMin > 0 ? `in ${diffMin} min` : "now";
}

function normalizeStatusLabel(status) {
    if (!status) return "";
    return status.replace(/\b\w/g, c => c.toUpperCase());
}

function setupTaskFeedbackModal() {
    const modal = document.getElementById("task-feedback-modal");
    if (!modal) return;

    const titleTime = modal.querySelector(".task-feedback-time");
    const titleName = modal.querySelector(".task-feedback-name");
    const statusButtons = modal.querySelectorAll(".feedback-option");
    const laterButton = modal.querySelector(".feedback-later");
    const queue = [];
    const queuedIds = new Set();
    let activeItem = null;

    function collectOverdueTasks() {
        const now = new Date();
        document.querySelectorAll(".todo-row").forEach(row => {
            const timeSlot = row.dataset.timeSlot;
            const status = (row.dataset.status || "").trim();
            if (!timeSlot || status) return;
            const endTime = parseSlotEndTime(timeSlot);
            if (!endTime) return;
            if (now >= endTime && !queuedIds.has(row.dataset.todoId)) {
                queue.push({
                    id: row.dataset.todoId,
                    timeSlot,
                    task: row.dataset.task || "",
                });
                queuedIds.add(row.dataset.todoId);
            }
        });
    }

    function openModal(item) {
        activeItem = item;
        titleTime.textContent = item.timeSlot;
        titleName.textContent = item.task ? `- ${item.task}` : "";
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
        activeItem = null;
    }

    function showNext() {
        if (activeItem || queue.length === 0) return;
        openModal(queue.shift());
    }

    function updateRowStatus(todoId, status) {
        const row = document.querySelector(`.todo-row[data-todo-id="${todoId}"]`);
        if (!row) return;
        queuedIds.delete(todoId);
        const statusEl = row.querySelector(".task-status");
        if (statusEl) {
            statusEl.dataset.status = status;
            statusEl.textContent = normalizeStatusLabel(status);
        }
        row.dataset.status = status;
        const taskInput = row.querySelector(`input[name="task_${todoId}"]`);
        const checkbox = row.querySelector(".complete-checkbox");
        if (checkbox) {
            checkbox.checked = true;
            checkbox.disabled = true;
        }
        if (taskInput) {
            taskInput.classList.add("done");
        }
    }

    statusButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            if (!activeItem) return;
            const status = btn.dataset.status;
            fetch("/todo/mark_status", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: activeItem.id,
                    status,
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        updateRowStatus(activeItem.id, status);
                        closeModal();
                        showNext();
                    } else {
                        alert("Status update failed.");
                    }
                })
                .catch(err => {
                    console.error("Status update error:", err);
                    alert("Error updating status.");
                });
        });
    });

    if (laterButton) {
        laterButton.addEventListener("click", () => {
            if (!activeItem) {
                closeModal();
                return;
            }

            const resumeItem = { ...activeItem };
            const taskInput = document.querySelector(`input[name="task_${resumeItem.id}"]`);
            closeModal();

            if (!taskInput) {
                openModal(resumeItem);
                return;
            }

            taskInput.focus();
            taskInput.select();

            const reopenModal = () => {
                taskInput.removeEventListener("blur", reopenModal);
                taskInput.removeEventListener("keydown", handleKeydown);
                openModal(resumeItem);
            };

            const handleKeydown = (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    reopenModal();
                }
            };

            taskInput.addEventListener("blur", reopenModal);
            taskInput.addEventListener("keydown", handleKeydown);
        });
    }

    collectOverdueTasks();
    showNext();
    setInterval(() => {
        if (activeItem) return;
        collectOverdueTasks();
        showNext();
    }, 60000);
}

setupTaskFeedbackModal();
setupAdminStatusDropdowns();
setupScheduleConfig();
setupTimeOptions();
updateSlotProgress();
setInterval(updateSlotProgress, 60000);
updateNowLine();
setInterval(updateNowLine, 60000);
updateNextMissionEta();
setInterval(updateNextMissionEta, 60000);

function getSlotDurationMinutes(timeSlot) {
    const startTime = parseSlotStartTime(timeSlot);
    const endTime = parseSlotEndTime(timeSlot);
    if (!startTime || !endTime) return null;
    return Math.round((endTime - startTime) / 60000);
}

function updateRowStatusFromDropdown(todoId, status) {
    const row = document.querySelector(`.todo-row[data-todo-id="${todoId}"]`);
    if (!row) return;
    row.dataset.status = status;
    const taskInput = row.querySelector(`input[name="task_${todoId}"]`);
    const checkbox = row.querySelector(".complete-checkbox");
    if (checkbox) {
        checkbox.checked = true;
        checkbox.disabled = true;
    }
    if (taskInput) {
        taskInput.classList.add("done");
    }
    const statusEl = row.querySelector(".task-status");
    if (statusEl) {
        statusEl.dataset.status = status;
        statusEl.textContent = normalizeStatusLabel(status);
    }
}

function setupAdminStatusDropdowns() {
    const selects = document.querySelectorAll(".admin-status-select");
    if (!selects.length) return;

    selects.forEach(select => {
        select.addEventListener("change", () => {
            const todoId = select.dataset.todoId;
            const status = select.value;
            if (!todoId) return;
            if (!status) return;
            fetch("/todo/mark_status", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: todoId,
                    status,
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        updateRowStatusFromDropdown(todoId, status);
                    } else {
                        alert("Status update failed.");
                    }
                })
                .catch(err => {
                    console.error("Status update error:", err);
                    alert("Error updating status.");
                });
        });
    });
}

function setupScheduleConfig() {
    const form = document.getElementById("schedule-config");
    if (!form) return;
    const modeSelect = form.querySelector("#schedule_mode");
    const customRow = form.querySelector(".config-custom-row");
    if (!modeSelect || !customRow) return;

    const toggleCustomRow = () => {
        const isCustom = modeSelect.value === "custom";
        customRow.classList.toggle("config-hidden", !isCustom);
    };

    toggleCustomRow();
    modeSelect.addEventListener("change", toggleCustomRow);
}

function setupTimeOptions() {
    const selects = document.querySelectorAll(".config-time-select");
    if (!selects.length) return;
    const options = [];
    for (let hour = 0; hour < 24; hour += 1) {
        for (let minute = 0; minute < 60; minute += 30) {
            options.push(`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
        }
    }

    selects.forEach(select => {
        if (select.dataset.ready === "true") return;
        select.innerHTML = "";
        options.forEach(value => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = value;
            select.appendChild(option);
        });
        if (select.id === "custom_end") {
            const option = document.createElement("option");
            option.value = "23:59";
            option.textContent = "23:59";
            select.appendChild(option);
        }
        const current = select.dataset.current;
        if (current) {
            select.value = current;
        }
        select.dataset.ready = "true";
    });
}

function setupCurrentSubtaskInputs() {
    document.querySelectorAll(".task-current-sub-input").forEach(input => {
        const hidden = document.getElementById(input.dataset.hiddenId);
        if (!hidden) return;
        input.addEventListener("input", () => {
            hidden.value = `${input.dataset.main}[${input.value}]`;
        });
    });
}

function setupSplitSlotButtons() {
    document.querySelectorAll(".split-slot-btn").forEach(btn => {
        const row = btn.closest(".todo-row");
        const timeSlot = row ? row.dataset.timeSlot : "";
        const duration = getSlotDurationMinutes(timeSlot);
        if (duration !== 60 && duration !== 59) {
            btn.disabled = true;
            btn.title = "Only 59-60-minute slots can be split.";
        }

        btn.addEventListener("click", () => {
            if (!row) return;
            const todoId = btn.dataset.todoId;
            if (!todoId || btn.disabled) return;
            fetch("/todo/split_slot", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: todoId,
                    username: selected_user_name
                })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert(data.error || "Split failed.");
                    }
                })
                .catch(err => {
                    console.error("Split error:", err);
                    alert("Error splitting slot.");
                });
        });
    });
}

function setupPlanDrawer() {
    const toggle = document.getElementById("sf-plan-drawer-toggle");
    const drawer = document.getElementById("sf-plan-drawer");
    const overlay = document.getElementById("sf-plan-drawer-overlay");
    const closeBtn = document.getElementById("sf-plan-drawer-close");
    if (!toggle || !drawer || !overlay) return;

    const DRAWER_OPEN_KEY = "sfPlanDrawerOpen";

    function openDrawer() {
        drawer.classList.add("open");
        overlay.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");
        sessionStorage.setItem(DRAWER_OPEN_KEY, "1");
    }

    function closeDrawer() {
        drawer.classList.remove("open");
        overlay.classList.remove("open");
        drawer.setAttribute("aria-hidden", "true");
        sessionStorage.removeItem(DRAWER_OPEN_KEY);
    }

    toggle.addEventListener("click", openDrawer);
    overlay.addEventListener("click", closeDrawer);
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeDrawer();
    });

    // The config selects submit the form (full page reload) on every change,
    // so re-open the drawer automatically after that reload instead of
    // making the user pull it out again for each field.
    if (sessionStorage.getItem(DRAWER_OPEN_KEY) === "1") {
        openDrawer();
    }
}

function setupHeatmapTooltips() {
    // The hover cards are position:fixed ::after boxes, so they need real
    // viewport coordinates: the browser's static-position fallback is
    // document-based and lands below the viewport once the page is scrolled.
    const cells = document.querySelectorAll(
        ".sf-heatmap-cell[data-tooltip], .sf-week-day .v[data-tooltip]"
    );
    cells.forEach((cell) => {
        cell.addEventListener("mouseenter", () => {
            const rect = cell.getBoundingClientRect();
            // Card is up to 280px wide and centered on --sf-tip-x; keep the
            // center far enough from the edges that it stays on screen.
            const centerX = rect.left + rect.width / 2;
            const x = Math.min(Math.max(centerX, 148), window.innerWidth - 148);
            // Card height varies with the day's task count, so show it on
            // whichever side of the cell has more room.
            const below = rect.top < window.innerHeight - rect.bottom;
            cell.style.setProperty("--sf-tip-x", `${x}px`);
            cell.style.setProperty("--sf-tip-y", `${below ? rect.bottom + 12 : rect.top - 12}px`);
            cell.toggleAttribute("data-tip-below", below);
        });
    });
}

setupSplitSlotButtons();
setupCurrentSubtaskInputs();
setupPlanDrawer();
setupHeatmapTooltips();