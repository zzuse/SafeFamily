The dump.sql file created most of the tables, but it missed the following table that your code actively tries to write to:

    agile_config: Used by helpers.py for dynamic configuration settings (like the show_disable_button_start setting we just updated).
    -- CREATE TABLE agile_config (
    --         id SERIAL PRIMARY KEY,
    --         config_key VARCHAR(100) UNIQUE NOT NULL,
    --         config_value TEXT NOT NULL,
    --         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- );

  ✅ Tables That Were Successfully Restored
  These tables exist in your dump.sql backup and were successfully restored when the container booted up:

  Core Application Tables:
   - users
   - auth_codes
   - token_blocklist

  Todo & Goals Tables:
   - todo_list
   - long_term_goals
   - long_term_goals_his

  Rules & Scheduling Tables:
   - schedule_rules
   - user_rule_assignment

  Logging & Filtering Tables:
   - logs
   - logs_daily
   - block_list
   - block_types
   - filter_rule
   - suspicious

  Notes & Syncing Tables (NoteSync):
   - notes
   - tags
   - note_tags
   - media
   - note_sync_ops