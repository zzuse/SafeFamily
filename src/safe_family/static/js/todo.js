
const element = document.getElementById("bridge-element");
const selected_user_row_id = element.dataset.value; // Access data-value
const selected_user_name = element.dataset.user;

document.getElementById("todoForm").addEventListener("submit", function (e) {
    const inputs = document.querySelectorAll(".task-input");
    const pattern = /^([^\[\]/]+\[[^\[\]]+\])(\s*\/\s*[^\[\]/]+\[[^\[\]]+\])*$/; // matches: main[sub]
    for (const input of inputs) {
        if (input.value.trim() !== "" && !pattern.test(input.value.trim())) {
            e.preventDefault();
            alert(`❌ Invalid format: "${input.value}". Use "main task[sub task]" format.`);
            input.focus();
            return;
        }
    }
});

document.querySelectorAll('.complete-checkbox').forEach(cb => {
    cb.addEventListener('change', function () {
        // Here will find data-task-id field in todo HTML
        const taskId = this.dataset.taskId;
        const completed = this.checked;

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
    let activeItem = null;

    function collectOverdueTasks() {
        const now = new Date();
        document.querySelectorAll(".todo-row").forEach(row => {
            const timeSlot = row.dataset.timeSlot;
            const status = (row.dataset.status || "").trim();
            const completed = row.dataset.completed === "true";
            if (!timeSlot || status || completed) return;
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
        const checkbox = row.querySelector(".complete-checkbox");
        const taskInput = row.querySelector(`input[name="task_${todoId}"]`);
        const isDone = status === "done";
        row.dataset.completed = isDone ? "true" : "false";
        if (checkbox) checkbox.checked = isDone;
        if (taskInput) {
            taskInput.classList.toggle("done", isDone);
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
updateSlotProgress();
setInterval(updateSlotProgress, 60000);

function getSlotDurationMinutes(timeSlot) {
    const startTime = parseSlotStartTime(timeSlot);
    const endTime = parseSlotEndTime(timeSlot);
    if (!startTime || !endTime) return null;
    return Math.round((endTime - startTime) / 60000);
}

function setupSplitSlotButtons() {
    document.querySelectorAll(".split-slot-btn").forEach(btn => {
        const row = btn.closest(".todo-row");
        const timeSlot = row ? row.dataset.timeSlot : "";
        const duration = getSlotDurationMinutes(timeSlot);
        if (duration !== 60) {
            btn.disabled = true;
            btn.title = "Only 60-minute slots can be split.";
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

// -------- below is not for TODO any more, for Long Term Goal -------

function attachHelperPopups() {
    document.querySelectorAll(".help-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const popup = btn.nextElementSibling;
            popup.classList.toggle("hidden");
        });
        btn.addEventListener("mouseenter", () => {
            btn.nextElementSibling.classList.remove("hidden");
        });
        btn.addEventListener("mouseleave", () => {
            btn.nextElementSibling.classList.add("hidden");
        });
    });

    document.addEventListener("click", () => {
        document.querySelectorAll(".help-popup").forEach(p => p.classList.add("hidden"));
    });
}

new Sortable(document.getElementById("longterm-list"), {
    animation: 150,
    delay: 400,
    handle: ".drag-handle",
    onEnd: function () {
        saveNewOrder();
        refreshTaskPos();
        refreshTaskColors();
    }
});

function saveNewOrder() {
    let ids = [...document.querySelectorAll("#longterm-list li")]
        .map(li => li.dataset.id);

    fetch("/todo/long_term_reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order: ids })
    });
}

const PRIORITY_LABELS = {
    1: "High",
    2: "Medium-High",
    3: "Medium",
    4: "Medium-Low",
    5: "Low"
};

/**
 * Map any priority range 1..maxValue into a 1..5 scale.
 * 1 = highest priority
 * 5 = lowest priority
 */
function mapPriorityToFiveLevels(priority, maxValue) {
    if (maxValue <= 1) return 1;  // only one level

    // Linear mapping to range [1..5]
    const normalized = (priority - 1) / (maxValue - 1); // range 0..1
    const scaled = Math.round(normalized * 4) + 1;      // range 1..5

    return Math.min(5, Math.max(1, scaled)); // clamp safety
}

function refreshTaskPos() {
    const items = document.querySelectorAll("#longterm-list li select option[selected]");

    items.forEach((el, index) => {
        const pos = index + 1; // new position

        // Re-apply based on new pos
        el.value = pos;
    });
}

function refreshTaskColors() {
    const items = document.querySelectorAll("#longterm-list li input[type='text']");
    color_length = items.length;

    items.forEach((el, index) => {
        const pos = index + 1; // new position

        // Remove previous color classes
        el.classList.remove("priority-1", "priority-2", "priority-3", "priority-4", "priority-5");
        // el.style.background = "#FFFFFF";
        // el.style.color = "#e6ffed";

        // Re-apply based on new pos
        level = mapPriorityToFiveLevels(pos, color_length)
        el.classList.add(`priority-${level}`);
    });
}

function renderShortDatePicker(container, pgTimestamp, options = {}, goal_id) {
    options = Object.assign({
        format: 'MMM DDD',
        locale: 'en',
        emptyText: 'DUE'
    }, options);

    const fakeSpan = document.createElement('span');
    fakeSpan.style.cssText = `
                cursor: pointer;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 14px;
                display: inline-block;
                min-width: 60px;
                text-align: center;
                user-select: none;
            `;

    container.dataset.goal_id = goal_id;

    let currentDate = null;
    if (pgTimestamp) {
        currentDate = new Date(pgTimestamp);
        if (isNaN(currentDate)) currentDate = null;
    }

    function updateDisplay() {
        if (currentDate) {
            const formatted = new Intl.DateTimeFormat(options.locale === 'en' ? 'en-US' : 'zh-CN', {
                month: 'short',
                day: 'numeric'
            }).format(currentDate);
            // console.log("formatted data ", formatted)
            fakeSpan.textContent = options.format
                .replace('MMM', formatted.split(' ')[0])
                .replace('DDD', formatted.split(' ')[1] || formatted.split(' ')[0]);
        } else {
            fakeSpan.textContent = options.emptyText;
        }
        // console.log("fakeSpan ", fakeSpan);
    }
    updateDisplay();

    const fp = flatpickr(fakeSpan, {
        dateFormat: "Y-m-d",
        defaultDate: currentDate,
        locale: options.locale === 'zh' ? "zh" : "default",
        clickOpens: true,
        allowInput: false,
        onChange: function (selectedDates, dateStr) {
            currentDate = selectedDates[0] || null;
            updateDisplay();
            container.dataset.due = currentDate.toISOString().split('T')[0] + 'T12:00:00'

            if (container.dataset.goal_id) {
                updateDueDateToServer(container.dataset.goal_id, container.dataset.due);
            }
        }
    });

    function updateDueDateToServer(goalId, dateStr) {
        fetch(`/todo/longterm_update_due/${goalId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ due_date: dateStr })
        });
    }

    container.innerHTML = '';
    container.appendChild(fakeSpan);

    return {
        getValue: () => currentDate ? fp.formatDate(currentDate, "Y-m-d") : null,
        setValue: (dateStr) => fp.setDate(dateStr, true)
    };
}

async function loadLongTerm() {
    let r = await fetch("/todo/long_term_list/" + selected_user_row_id, {
        headers: { "Authorization": "Bearer " + localStorage.getItem("access_token") }
    });
    let tasks = await r.json();

    let container = document.getElementById("longterm-list");
    container.innerHTML = "";

    color_length = tasks.length;

    tasks.forEach(t => {
        let li = document.createElement("li");

        li.addEventListener("keydown", function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                updateLongTerm(t.goal_id, color_length);
            }
        });

        li.setAttribute("data-id", t.goal_id);

        li.innerHTML = `
                <div class="grid grid-cols-46">
                    <div class="col-span-24 justify-between items-center text-center">
                        <input type="checkbox" id="check_${t.goal_id}" ${t.completed ? "checked" : ""} onchange="updateLongTerm(${t.goal_id}, ${color_length})">

                        <input type="text" id="task_${t.goal_id}" value="${t.task}" class="drag-handle ${t.completed ? "done" : ""}
                            text-[#ecf0f1] priority-${mapPriorityToFiveLevels(t.priority, color_length)}"
                            style="width: 95%; margin-bottom: 5px; margin-top: 5px;">

                        <select class="hidden priority-${mapPriorityToFiveLevels(t.priority, color_length)} text-[#ecf0f1]"
                            id="prio_${t.goal_id}" onchange="updateLongTerm(${t.goal_id}, ${color_length})">
                            ${[1, 2, 3, 4, 5].map(p =>
            `<option value="${t.priority}" ${p == mapPriorityToFiveLevels(t.priority, color_length) ? "selected" : ""}>
                                ${PRIORITY_LABELS[p]}
                            </option>`
        ).join("")}
                        </select>
                    </div>
                    <div class="col-span-22 flex justify-between items-center text-center">
                        <span class="short-date w-3/11" data-due="${t.due_date || ''}"></span>

                        <span class="time-spent w-3/11 min-w-10" id="time-${t.goal_id}">
                            ${formatSeconds(t.time_spent)}
                        </span>

                        <button class="timer-btn w-4/11 min-w-20 ${t.is_tracking ? "stop text-purple-300" : "start text-green-300"}">
                            ${t.is_tracking ? "⏸ Pause" : "▶ Start"}
                        </button>
                        <div class="menu-container w-1/11">
                            <button class="menu-btn text-gray-400 hover:text-gray-600 transition-colors">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-ellipsis-vertical w-5 h-5" aria-hidden="true">
                                    <circle cx="12" cy="12" r="1"></circle>
                                    <circle cx="12" cy="5" r="1"></circle>
                                    <circle cx="12" cy="19" r="1"></circle>
                                </svg>
                            </button>
                            <div class="menu-popup hidden">
                                <div class="menu-item delete-item" data-goal-id="${t.goal_id}">
                                    ❌ Delete
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                `;

        li.querySelectorAll('.short-date').forEach(el => {
            renderShortDatePicker(el, el.dataset.due, {
                format: 'MMM DDD',
                locale: 'en',
                emptyText: '-'
            }, t.goal_id);
        });

        li.querySelectorAll('.timer-btn').forEach(el => {
            startGoalTracking(el, t.is_tracking, t.goal_id);
        });

        // Toggle popup
        li.querySelectorAll(".menu-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const popup = btn.nextElementSibling;
                popup.classList.toggle("hidden");
            });
        });

        // Delete item
        li.querySelectorAll(".delete-item").forEach(item => {
            item.addEventListener("click", handleDeleteGoal);
        });

        // Close popups when clicking outside
        document.addEventListener("click", () => {
            document.querySelectorAll(".menu-popup").forEach(p => p.classList.add("hidden"));
        });

        container.appendChild(li);
    });
}

async function updateLongTerm(goal_id, color_length) {
    let body = {
        goal_id,
        color_length,
        task: document.getElementById("task_" + goal_id).value,
        priority: document.getElementById("prio_" + goal_id).value,
        completed: document.querySelector(`#longterm-list input[type='checkbox'][onchange='updateLongTerm(${goal_id}, ${color_length})']`).checked,
    };

    await fetch("/todo/long_term_update", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + localStorage.getItem("access_token")
        },
        body: JSON.stringify(body)
    });

    loadLongTerm();
}

document.getElementById("add-longterm-form").addEventListener("submit", async e => {
    e.preventDefault();
    const pattern = /^([^\[\]/]+\[[^\[\]]+\])(\s*\/\s*[^\[\]/]+\[[^\[\]]+\])*$/; // matches: main[sub]
    input = document.getElementById("longterm-task-text")
    if (input.value.trim() !== "" && !pattern.test(input.value.trim())) {
        alert(`❌ Invalid format: "${input.value}". Use "Object[Problem]" format.`);
        input.focus();
        return;
    } else if (input.value.trim() === "") {
        alert(`❌ Can't be NULL: "${input.value}". Use "Object[Problem]" format.`);
        input.focus();
        return;
    }

    await fetch("/todo/long_term_add", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + localStorage.getItem("access_token")
        },
        body: JSON.stringify({
            user_id: selected_user_row_id,
            task: document.getElementById("longterm-task-text").value,
            priority: document.getElementById("longterm-priority").value
        })
    });

    document.getElementById("longterm-task-text").value = "";
    loadLongTerm();
});

function formatSeconds(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}

function startGoalTracking(btn, is_tracking, goal_id) {
    btn.dataset.goal_id = goal_id;
    btn.dataset.is_tracking = String(is_tracking);
    btn.addEventListener("click", () => {
        const isTracking = btn.dataset.is_tracking === "true";
        // console.log("Before:", btn.dataset.is_tracking)
        // update DB
        const url = isTracking
            ? `/todo/longterm_stop/${goal_id}`
            : `/todo/longterm_start/${goal_id}`;

        fetch(url, { method: "POST" })
            .then(r => r.json())
            .then(data => {
                // console.log("DB updated", data);
                if (data.time_spent !== undefined) {
                    const timeSpan = document.querySelector(`#time-${goal_id}`);
                    timeSpan.textContent = formatSeconds(data.time_spent);
                }
            });
        // update UI
        btn.dataset.is_tracking = String(!isTracking);
        // console.log("After:", btn.dataset.is_tracking)
        if (btn.dataset.is_tracking === "true") {
            btn.classList.remove("start");
            btn.classList.remove("text-green-300");
            btn.classList.add("stop");
            btn.classList.add("text-purple-300");
            btn.innerText = "⏸ Pause";
        } else {
            btn.classList.remove("stop");
            btn.classList.remove("text-purple-300");
            btn.classList.add("start");
            btn.classList.add("text-green-300");
            btn.innerText = "▶ Start";
        }
    });
}

function handleDeleteGoal(e) {
    const goalId = e.target.dataset.goalId;

    fetch(`/todo/longterm_delete/${goalId}`, { method: "POST" })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const li = document.querySelector(`li[data-id="${goalId}"]`);
                if (li) li.remove();
            }
        })
        .catch(err => console.error("Delete error:", err));
}

loadLongTerm();
attachHelperPopups();
