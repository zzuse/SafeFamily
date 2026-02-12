const element = document.getElementById("bridge-element");
const selected_user_row_id = element.dataset.value; // Access data-value
const selected_user_name = element.dataset.user;
const selected_user_role = element.dataset.role;

const notifyCurrentTaskBtn = document.querySelector(".notify-current-task-btn");
if (notifyCurrentTaskBtn) {
    notifyCurrentTaskBtn.addEventListener("click", () => {
        notifyCurrentTaskBtn.disabled = true;
        const payload = selected_user_name ? { username: selected_user_name } : {};
        fetch("/todo/notify_current_task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then(r => r.json())
            .then(data => {
                if (!data.success) {
                    alert(data.error || "Notify failed.");
                }
            })
            .catch(err => {
                console.error("Notify failed:", err);
                alert("Notify failed.");
            })
            .finally(() => {
                notifyCurrentTaskBtn.disabled = false;
            });
    });
}

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
    document.querySelectorAll(".time-slot-cell").forEach(cell => {
        const timeSlot = cell.dataset.timeSlot;
        const startTime = parseSlotStartTime(timeSlot);
        const endTime = parseSlotEndTime(timeSlot);
        if (!startTime || !endTime) return;

        const total = endTime - startTime;
        if (total <= 0) return;

        let progress = (now - startTime) / total;
        if (progress < 0) progress = 0;
        if (progress > 1) progress = 1;
        cell.style.setProperty("--slot-fill", `${Math.round(progress * 100)}%`);
        cell.dataset.slotProgress = progress.toFixed(3);

        const row = cell.closest(".todo-row");
        if (!row) return;
        const checkbox = row.querySelector(".complete-checkbox");
        const status = (row.dataset.status || "").trim();
        const completed = row.dataset.completed === "true";
        const taskInput = row.querySelector(`input[name="task_${row.dataset.todoId}"]`);
        const isActive = now >= startTime && now < endTime && !completed;
        cell.classList.toggle("is-active", isActive);
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
    const serverNotifiedIds = new Set();
    let activeItem = null;

    function sendTaskFeedbackServerAlert(item) {
        if (serverNotifiedIds.has(item.id)) return;
        fetch("/todo/notify_feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                time_slot: item.timeSlot,
                task: item.task || "",
            }),
        }).catch(err => {
            console.warn("Server alert failed:", err);
        });
        serverNotifiedIds.add(item.id);
    }

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
        sendTaskFeedbackServerAlert(item);
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

function setupWeeklySummaryPopup() {
    const modal = document.getElementById("weekly-summary-modal");
    if (!modal) return;

    const contentEl = modal.querySelector(".weekly-summary-content");
    const subtitleEl = modal.querySelector(".weekly-summary-subtitle");
    const closeButtons = modal.querySelectorAll(".weekly-summary-close, .weekly-summary-close-btn");
    const bridge = document.getElementById("bridge-element");
    const selectedUser = bridge ? bridge.dataset.user : "";

    function pad2(value) {
        return String(value).padStart(2, "0");
    }

    function localDateKey(date) {
        return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
    }


    function closeModal() {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
    }

    function openModal() {
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
    }

    closeButtons.forEach(button => {
        button.addEventListener("click", closeModal);
    });

    modal.addEventListener("click", event => {
        if (event.target === modal) {
            closeModal();
        }
    });

    function fetchSummary() {
        const params = new URLSearchParams();
        if (selectedUser) {
            params.set("user", selectedUser);
        }
        const url = params.toString()
            ? `/todo/weekly_summary?${params.toString()}`
            : "/todo/weekly_summary";

        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    throw new Error(data.error || "Summary unavailable");
                }
                subtitleEl.textContent = data.week ? `Week ${data.week}` : "Weekly summary";
                contentEl.textContent = data.summary || "No summary data available.";
                openModal();
                localStorage.setItem("weeklySummaryShown", localDateKey(new Date()));
            })
            .catch(err => {
                console.warn("Weekly summary failed:", err);
                subtitleEl.textContent = "Weekly summary";
                contentEl.textContent = "Summary unavailable right now.";
                openModal();
                localStorage.setItem("weeklySummaryShown", localDateKey(new Date()));
            })
            .finally(() => {
                scheduleNext();
            });
    }

    function scheduleNext() {
        const now = new Date();
        const target = new Date(now);
        target.setHours(15, 30, 0, 0);
        if (now >= target) {
            target.setDate(target.getDate() + 1);
        }
        const delay = Math.max(target - now, 0);
        window.setTimeout(fetchSummary, delay);
    }

    const now = new Date();
    const todayKey = localDateKey(now);
    const target = new Date(now);
    target.setHours(15, 30, 0, 0);
    if (now >= target && localStorage.getItem("weeklySummaryShown") !== todayKey) {
        fetchSummary();
        return;
    }
    scheduleNext();
}

function setupUnknownMetadataFlow() {
    const tagsModal = document.getElementById("unknown-tags-modal");
    const statusModal = document.getElementById("unknown-status-modal");
    if (!tagsModal || !statusModal) return;

    const tagsList = tagsModal.querySelector(".unknown-tags-list");
    const statusList = statusModal.querySelector(".unknown-status-list");
    const tagsSave = tagsModal.querySelector(".unknown-tags-save");
    const tagsSkip = tagsModal.querySelector(".unknown-tags-skip");
    const tagsClose = tagsModal.querySelector(".unknown-tags-close");
    const statusSave = statusModal.querySelector(".unknown-status-save");
    const statusSkip = statusModal.querySelector(".unknown-status-skip");
    const statusClose = statusModal.querySelector(".unknown-status-close");
    const bridge = document.getElementById("bridge-element");
    const selectedUser = bridge ? bridge.dataset.user : "";
    let pendingStatusItems = [];

    const tagOptions = ["math", "science", "language", "coding", "leasure", "piano", "unknown"];
    const statusOptions = ["skipped", "partially done", "half done", "mostly done", "done"];

    function setModalState(modal, isOpen) {
        if (isOpen) {
            modal.classList.add("active");
            modal.setAttribute("aria-hidden", "false");
        } else {
            modal.classList.remove("active");
            modal.setAttribute("aria-hidden", "true");
        }
    }

    function renderTags(items) {
        tagsList.innerHTML = "";
        items.forEach(item => {
            const row = document.createElement("div");
            row.className = "unknown-tags-row";
            row.dataset.todoId = item.id;
            const title = document.createElement("div");
            title.className = "unknown-row-title";
            title.textContent = item.time_slot
                ? `${item.time_slot} - ${item.task}`
                : item.task;
            const select = document.createElement("select");
            tagOptions.forEach(option => {
                const opt = document.createElement("option");
                opt.value = option;
                opt.textContent = option;
                if (option === (item.tags || "unknown")) {
                    opt.selected = true;
                }
                select.appendChild(opt);
            });
            row.appendChild(title);
            row.appendChild(select);
            tagsList.appendChild(row);
        });
    }

    function renderStatus(items) {
        statusList.innerHTML = "";
        items.forEach(item => {
            const row = document.createElement("div");
            row.className = "unknown-status-row";
            row.dataset.todoId = item.id;
            const title = document.createElement("div");
            title.className = "unknown-row-title";
            title.textContent = item.time_slot
                ? `${item.time_slot} - ${item.task}`
                : item.task;
            const select = document.createElement("select");
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "Select status";
            placeholder.selected = true;
            select.appendChild(placeholder);
            statusOptions.forEach(option => {
                const opt = document.createElement("option");
                opt.value = option;
                opt.textContent = option;
                select.appendChild(opt);
            });
            row.appendChild(title);
            row.appendChild(select);
            statusList.appendChild(row);
        });
    }

    function openStatusIfNeeded() {
        if (!pendingStatusItems.length) return;
        renderStatus(pendingStatusItems);
        setModalState(statusModal, true);
    }

    function closeTagsModal() {
        setModalState(tagsModal, false);
    }

    function closeStatusModal() {
        setModalState(statusModal, false);
    }

    [tagsClose, tagsSkip].forEach(btn => {
        if (btn) {
            btn.addEventListener("click", () => {
                closeTagsModal();
                openStatusIfNeeded();
            });
        }
    });

    [statusClose, statusSkip].forEach(btn => {
        if (btn) {
            btn.addEventListener("click", closeStatusModal);
        }
    });

    if (tagsSave) {
        tagsSave.addEventListener("click", () => {
            const updates = [];
            tagsList.querySelectorAll(".unknown-tags-row").forEach(row => {
                const todoId = row.dataset.todoId;
                const select = row.querySelector("select");
                const tag = select ? select.value : "";
                if (todoId && tag && tag !== "unknown") {
                    updates.push(
                        fetch("/todo/update_tag", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ id: todoId, tag }),
                        }).catch(err => {
                            console.warn("Tag update failed:", err);
                        })
                    );
                }
            });
            Promise.all(updates).finally(() => {
                closeTagsModal();
                openStatusIfNeeded();
            });
        });
    }

    if (statusSave) {
        statusSave.addEventListener("click", () => {
            const updates = [];
            statusList.querySelectorAll(".unknown-status-row").forEach(row => {
                const todoId = row.dataset.todoId;
                const select = row.querySelector("select");
                const status = select ? select.value : "";
                if (todoId && status) {
                    updates.push(
                        fetch("/todo/mark_status", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ id: todoId, status }),
                        }).catch(err => {
                            console.warn("Status update failed:", err);
                        })
                    );
                }
            });
            Promise.all(updates).finally(() => {
                closeStatusModal();
            });
        });
    }

    function fetchUnknownMetadata() {
        const params = new URLSearchParams();
        if (selectedUser) {
            params.set("user", selectedUser);
        }
        const url = params.toString()
            ? `/todo/unknown_metadata?${params.toString()}`
            : "/todo/unknown_metadata";
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    throw new Error(data.error || "Unknown metadata unavailable");
                }
                const tags = data.unknown_tags || [];
                const status = data.unknown_status || [];
                pendingStatusItems = status;
                if (tags.length) {
                    renderTags(tags);
                    setModalState(tagsModal, true);
                    return;
                }
                if (status.length) {
                    openStatusIfNeeded();
                }
            })
            .catch(err => {
                console.warn("Unknown metadata failed:", err);
            });
    }

    fetchUnknownMetadata();
}

setupTaskFeedbackModal();
setupWeeklySummaryPopup();
if (shouldRunUnknownMetadataFlow()) {
    setupUnknownMetadataFlow();
}
setupAdminStatusDropdowns();
setupScheduleConfig();
setupTimeOptions();
updateSlotProgress();
setInterval(updateSlotProgress, 60000);

function shouldRunUnknownMetadataFlow(now = new Date()) {
    if (selected_user_role !== "admin") return false;
    if (now.getDay() !== 0) return false;
    return now.getHours() >= 16;
}

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

setupSplitSlotButtons();