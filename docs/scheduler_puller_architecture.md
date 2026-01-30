# 调度器与日志拉取系统架构说明

## 1. 背景与目标

本系统运行于 **7×24 小时在线的 Flask 后端服务** 中，采用 **gunicorn 多 worker（`-w 4`）** 部署模式。系统需要在以下约束下稳定运行：

- 多进程并发（gunicorn workers）
- 无额外守护进程（不使用 cron / systemd timer）
- 定时任务必须 **全局唯一执行**
- 后端需长期稳定运行，可自动恢复
- AdGuard Home 日志需 **可靠拉取、不重复、不遗漏（工程可接受级）**

为此，系统设计并实现了一套 **基于 APScheduler + PostgreSQL advisory lock 的 Leader / Job 锁调度架构**。

---

## 2. 总体架构概览

```
                ┌─────────────────────────┐
                │        Gunicorn          │
                │   (4 Worker Processes)   │
                └──────────┬──────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                  │                  │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼───────┐
│ Worker A       │  │ Worker B       │  │ Worker C       │
│ APScheduler    │  │ APScheduler    │  │ APScheduler    │
│                │  │                │  │                │
│  try leader    │  │  try leader    │  │  try leader    │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └───────────┬──────┴──────┬───────────┘
                    │  PostgreSQL │
                    │ advisory    │
                    │ locks       │
                    └──────┬──────┘
                           │
                  ┌────────▼────────┐
                  │  Leader Worker   │
                  │ (唯一调度执行者) │
                  └────────┬────────┘
                           │
                   ┌───────▼────────┐
                   │ Job-level Lock  │
                   │ (per job)       │
                   └───────┬────────┘
                           │
                   ┌───────▼────────┐
                   │  AdGuard Puller │
                   │  (API Pull)     │
                   └────────────────┘
```

---

## 3. 核心设计思想

### 3.1 单 Leader 调度模型

- 每个 gunicorn worker 都会启动 APScheduler
- 所有 worker **竞争同一个 PostgreSQL advisory lock**
- **只有成功获得 leader 锁的进程** 才被视为 Scheduler Leader
- Leader 锁 **依附于数据库连接**：
  - 进程崩溃 / 连接断开 → 锁自动释放
  - 其他 worker 可自动接管

该机制确保：

> 在任意时刻，全系统 **只有一个调度者在执行定时任务**

---

### 3.2 双层锁设计（Leader Lock + Job Lock）

#### 第一层：Scheduler Leader Lock

- 全局唯一
- 控制“是否允许执行调度任务”
- 防止多 worker 同时触发调度逻辑

#### 第二层：Per-Job Advisory Lock

- 每个 job 有一个独立的 advisory lock key
- Job 锁在 job 生命周期内持有
- 防止：
  - 重复执行
  - job 被多个 scheduler 同时运行

这种双层锁结构提供了 **强幂等与高安全性**。

---

## 4. 调度任务执行流程

1. APScheduler 触发 job
2. Job wrapper 执行以下检查：
   1. 是否为 Scheduler Leader
   2. 是否成功获得该 job 的 advisory lock
3. 若任一条件不满足：
   - Job 被安全跳过（`_JOB_SKIPPED`）
4. 若满足条件：
   - 执行实际业务逻辑（如 AdGuard 日志拉取）

此流程保证：

- 多 worker 环境下 **最多一次执行**
- Leader 切换期间不会产生并发执行

---

## 5. AdGuard 日志拉取（Puller）设计

### 5.1 拉取方式

- 通过 AdGuard Home `/control/querylog` API
- 不读取磁盘日志，不依赖 logrotate
- 拉取内存 query log，稳定性高

### 5.2 幂等与去重

- `qh` 字段：
  - 语义固定为 **domain**（前端依赖）
- `ip` 字段：
  - 复用为 **内部去重 hash**
- 去重 hash 来源：
  - `time + domain + qtype`
- 数据库层：
  - `ip` 字段建立 UNIQUE index
  - `ON CONFLICT DO NOTHING`

### 5.3 防遗漏策略

- 拉取时使用时间 overlap（如 2 秒）
- 每次 pull 拉取最新 N 条
- 即使重复拉取，也不会重复入库

该策略实现 **工程级 exactly-once 效果**。

---

## 6. Schedule 热更新机制

### LISTEN / NOTIFY

- PostgreSQL channel：`schedule_rules_changed`
- Scheduler 进程监听该 channel
- 收到通知后：
  - 重新加载调度规则

### 特点

- 无轮询
- 即时生效
- 多进程安全

### Why use this? 
    It is much better than "polling" (checking the DB every 5 seconds). It is instant, uses almost zero CPU when idle, and ensures all your workers stay in sync.
    This line uses PostgreSQL's built-in "Pub/Sub" (Publish/Subscribe) mechanism to synchronize your multiple Gunicorn worker processes.
    Since you are running gunicorn with multiple workers (e.g., -w 4), you actually have 4 separate copies of your application running. If a user updates a schedule in the Web UI, that request is handled by only one worker. Without this mechanism, the other 3 workers would continue running the old schedule.

### How it works:

   1. The Channel (`schedule_rules_changed`): Think of this as a radio frequency.
   2. The Listener (`LISTEN`):
       * Every worker starts a background thread (_listen_for_schedule_changes).
       * This thread connects to the DB and tunes into the "radio station" by executing LISTEN schedule_rules_changed.
       * It then goes to sleep (using select), waiting for a signal.
   3. The Notification (`NOTIFY`):
       * When you save a rule in the UI (schedule_rules route), the code calls notify_schedule_change().
       * This sends a broadcast signal: NOTIFY schedule_rules_changed.
   4. The Reaction:
       * PostgreSQL instantly wakes up all the listening threads in every worker.
       * They see the signal and run load_schedules() to fetch the new rules from the database.

---

## 7. 稳定性与容错设计

| 场景 | 行为 |
|----|----|
| Worker 崩溃 | Leader 锁释放，其他 worker 接管 |
| DB 连接断开 | 自动 re-elect leader |
| Job 重复触发 | Advisory lock 拦截 |
| 服务重启 | Scheduler 自动恢复 |

---

## 8. 设计取舍说明

### 为什么选择 APScheduler？

- 已存在多进程 leader 锁实现
- 支持 misfire / job lifecycle
- 与 Flask 生命周期可控集成

### 为什么不用 cron / systemd？

- 不引入额外进程
- 更易与业务逻辑共享上下文
- 更容易做幂等与状态控制

---

## 9. Threading.Lock

Here is why your process is multi-threaded, even if you didn't explicitly intend it to be:

   1. The Background Scheduler
      Line 223: scheduler = BackgroundScheduler()
      The APScheduler library starts its own background thread (and often a pool of worker threads) to check the time and execute jobs. This runs independently of your main application code.

   2. The Listener Thread
      Line 160: _LISTENER_THREAD = threading.Thread(...)
      Your code explicitly creates and starts a separate thread to listen for database notifications (LISTEN schedule_rules_changed). This thread runs forever in the background, waiting for signals.

   3. The Web Request (Flask)
      When you run this with Flask (especially in production with gunicorn), web requests often happen in their own thread (or at least the "main" thread), separate from the background tasks.

  The Danger Scenario (Race Condition)

  Without locks, here is a very real crash that could happen:

   1. Thread A (Web Request): You click "Save" on a rule in the browser. The web route calls load_schedules(). It starts deleting old jobs to replace them.
   2. Thread B (Listener): At the exact same millisecond, the database notifies your app that data changed. The listener thread also calls load_schedules().
   3. Crash: Thread A is halfway through deleting jobs when Thread B tries to add new ones. The internal list of jobs gets corrupted, and the scheduler crashes or runs tasks twice.

  The _LOAD_SCHEDULES_LOCK ensures that if the Web Request is reloading the schedule, the Listener has to wait its turn, preventing this collision.

  threading.Lock is used as a synchronization mechanism to prevent race conditions. A race condition occurs when multiple threads try to access and modify the same shared data at the same time, leading to unpredictable and incorrect results.

  Think of a threading.Lock as a key to a room. Only one thread can hold the key at any given time. If a thread wants to enter the "room" (execute a critical section of code), it must acquire the key (the lock). If another thread already has the key, the new thread must wait until the key is released.

  Here's how the different locks are used in this file:

   1. `_LOAD_SCHEDULES_LOCK = threading.Lock()`
       * Purpose: This lock is used inside the load_schedules function.
       * How it works: It ensures that only one thread can modify the scheduler's jobs at any given time. Reloading schedules involves removing all existing jobs and adding new ones from the database. This lock prevents a situation where two threads might try to reload schedules simultaneously, which
         could corrupt the scheduler's state.

   2. `_JOB_LOCKS_LOCK = threading.Lock()`
       * Purpose: This lock protects the _JOB_LOCKS dictionary.
       * How it works: The _JOB_LOCKS dictionary holds database connections that maintain advisory locks for each scheduled job. This is part of a mechanism to ensure that even if you have multiple copies of this application running, a specific scheduled job (like rule_disable_ai) only runs once across
         all of them. The _JOB_LOCKS_LOCK ensures that operations on this dictionary (adding or removing connections) are thread-safe within a single process.

   3. `_LISTENER_LOCK = threading.Lock()`
       * Purpose: This lock is used in the _start_schedule_listener function.
       * How it works: It guarantees that the background thread responsible for listening to schedule changes (_LISTENER_THREAD) is only created and started once. It prevents a race condition where multiple threads might simultaneously check if the listener thread exists, see that it doesn't, and then
         all try to start their own listener thread.

   4. `_SCHEDULER_LEADER_LOCK = threading.Lock()`
       * Purpose: This lock protects the global variables (_IS_SCHEDULER_LEADER, _SCHEDULER_LEADER_CONN) that are used for the "scheduler leader election".
       * How it works: In a multi-process setup, one process is elected as the "leader" to run the jobs. This lock ensures that the logic for checking and updating this leadership status is atomic (happens as a single, uninterruptible operation) within a single process. This prevents a thread from
         trying to re-elect a leader while another thread is in the middle of using the existing leader connection.

  In summary, threading.Lock is used throughout this file to protect shared resources and ensure the scheduler runs correctly and consistently, especially in a multi-threaded environment.

---

## 10. 总结

本架构是一套 **面向长期运行、多进程并发、强一致性要求的后端调度方案**：

- 以 PostgreSQL advisory lock 作为一致性基石
- APScheduler 仅作为触发器，而非控制器
- 核心逻辑完全掌控在应用代码中

该设计适合：

- 家庭 / 小型网络基础设施服务
- 内部日志采集与分析系统
- 对稳定性要求高于吞吐的后端服务

---

> 本系统的目标不是“最简单”，而是 **长期稳定、可解释、可维护**。

