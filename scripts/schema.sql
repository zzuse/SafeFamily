--
-- PostgreSQL database dump
--


-- Dumped from database version 15.16
-- Dumped by pg_dump version 15.16

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pageinspect; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pageinspect WITH SCHEMA public;


--
-- Name: EXTENSION pageinspect; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pageinspect IS 'inspect the contents of database pages at a low level';


--
-- Name: pgstattuple; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgstattuple WITH SCHEMA public;


--
-- Name: EXTENSION pgstattuple; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgstattuple IS 'show tuple-level statistics';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agile_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agile_config (
    id integer NOT NULL,
    config_key character varying(100) NOT NULL,
    config_value text NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: agile_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agile_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agile_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agile_config_id_seq OWNED BY public.agile_config.id;


--
-- Name: audit_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_item (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: audit_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_item_id_seq OWNED BY public.audit_item.id;


--
-- Name: audit_mark; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_mark (
    id integer NOT NULL,
    item_id integer NOT NULL,
    user_id character varying NOT NULL,
    mark_date date NOT NULL,
    value character varying(3) NOT NULL,
    updated_at timestamp without time zone,
    CONSTRAINT audit_mark_value_check CHECK (((value)::text = ANY ((ARRAY['yes'::character varying, 'no'::character varying])::text[])))
);


--
-- Name: audit_mark_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_mark_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_mark_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_mark_id_seq OWNED BY public.audit_mark.id;


--
-- Name: auth_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_codes (
    id integer NOT NULL,
    code_hash character varying(64) NOT NULL,
    user_id text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used_at timestamp without time zone
);


--
-- Name: auth_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_codes_id_seq OWNED BY public.auth_codes.id;


--
-- Name: block_list; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.block_list (
    id integer NOT NULL,
    qh text NOT NULL,
    type text
);


--
-- Name: block_list_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.block_list_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: block_list_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.block_list_id_seq OWNED BY public.block_list.id;


--
-- Name: block_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.block_types (
    id integer NOT NULL,
    name text NOT NULL
);


--
-- Name: block_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.block_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: block_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.block_types_id_seq OWNED BY public.block_types.id;


--
-- Name: countdown_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.countdown_config (
    id integer NOT NULL,
    user_id character varying NOT NULL,
    target_date character varying(10) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: countdown_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.countdown_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: countdown_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.countdown_config_id_seq OWNED BY public.countdown_config.id;


--
-- Name: filter_rule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.filter_rule (
    qh text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logs (
    id integer NOT NULL,
    "timestamp" timestamp with time zone NOT NULL,
    ip text,
    qh text,
    is_filtered boolean
);


--
-- Name: logs_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logs_daily (
    date date NOT NULL,
    qh text NOT NULL,
    count integer NOT NULL
);


--
-- Name: logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logs_id_seq OWNED BY public.logs.id;


--
-- Name: long_term_goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.long_term_goals (
    goal_id integer NOT NULL,
    user_id character varying,
    task_text text NOT NULL,
    priority integer DEFAULT 3,
    completed boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now(),
    completed_at timestamp without time zone,
    due_date timestamp without time zone,
    time_spent integer DEFAULT 0,
    is_tracking boolean DEFAULT false,
    tracking_start timestamp without time zone
);


--
-- Name: long_term_goals_goal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.long_term_goals_goal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: long_term_goals_goal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.long_term_goals_goal_id_seq OWNED BY public.long_term_goals.goal_id;


--
-- Name: long_term_goals_his; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.long_term_goals_his (
    goal_id integer NOT NULL,
    user_id character varying,
    task_text text NOT NULL,
    priority integer,
    completed_at timestamp without time zone,
    time_spent integer DEFAULT 0
);


--
-- Name: media; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media (
    id text NOT NULL,
    note_id text NOT NULL,
    user_id text NOT NULL,
    kind text NOT NULL,
    filename text NOT NULL,
    content_type text NOT NULL,
    checksum text NOT NULL,
    data bytea NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: note_sync_ops; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_sync_ops (
    id integer NOT NULL,
    user_id text NOT NULL,
    op_id text NOT NULL,
    note_id text NOT NULL,
    result text NOT NULL,
    applied_at timestamp without time zone NOT NULL
);


--
-- Name: note_sync_ops_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_sync_ops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_sync_ops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_sync_ops_id_seq OWNED BY public.note_sync_ops.id;


--
-- Name: note_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_tags (
    note_id text NOT NULL,
    tag_id text NOT NULL
);


--
-- Name: notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notes (
    id text NOT NULL,
    user_id text NOT NULL,
    text text NOT NULL,
    is_pinned boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone
);


--
-- Name: schedule_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedule_rules (
    id integer NOT NULL,
    rule_name text NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone,
    enabled boolean DEFAULT true NOT NULL,
    day_of_week text DEFAULT '*'::text
);


--
-- Name: schedule_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.schedule_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: schedule_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.schedule_rules_id_seq OWNED BY public.schedule_rules.id;


--
-- Name: suspicious; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suspicious (
    date date NOT NULL,
    qh text NOT NULL,
    count integer NOT NULL
);


--
-- Name: tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tags (
    id text NOT NULL,
    user_id text NOT NULL,
    name text NOT NULL
);


--
-- Name: todo_list; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.todo_list (
    id integer NOT NULL,
    time_slot text NOT NULL,
    task text,
    date date DEFAULT CURRENT_DATE,
    username character varying,
    completed boolean DEFAULT false,
    tags character varying,
    completion_status text
);


--
-- Name: todo_list_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.todo_list_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: todo_list_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.todo_list_id_seq OWNED BY public.todo_list.id;


--
-- Name: token_blocklist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.token_blocklist (
    id integer NOT NULL,
    jti character varying NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: token_blocklist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.token_blocklist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: token_blocklist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.token_blocklist_id_seq OWNED BY public.token_blocklist.id;


--
-- Name: user_rule_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_rule_assignment (
    id integer NOT NULL,
    user_id character varying,
    assigned_rule character varying(100)
);


--
-- Name: user_rule_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_rule_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_rule_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_rule_assignment_id_seq OWNED BY public.user_rule_assignment.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id character varying NOT NULL,
    username character varying NOT NULL,
    email character varying NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(20),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: agile_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agile_config ALTER COLUMN id SET DEFAULT nextval('public.agile_config_id_seq'::regclass);


--
-- Name: audit_item id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_item ALTER COLUMN id SET DEFAULT nextval('public.audit_item_id_seq'::regclass);


--
-- Name: audit_mark id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_mark ALTER COLUMN id SET DEFAULT nextval('public.audit_mark_id_seq'::regclass);


--
-- Name: auth_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_codes ALTER COLUMN id SET DEFAULT nextval('public.auth_codes_id_seq'::regclass);


--
-- Name: block_list id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_list ALTER COLUMN id SET DEFAULT nextval('public.block_list_id_seq'::regclass);


--
-- Name: block_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_types ALTER COLUMN id SET DEFAULT nextval('public.block_types_id_seq'::regclass);


--
-- Name: countdown_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countdown_config ALTER COLUMN id SET DEFAULT nextval('public.countdown_config_id_seq'::regclass);


--
-- Name: logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs ALTER COLUMN id SET DEFAULT nextval('public.logs_id_seq'::regclass);


--
-- Name: long_term_goals goal_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.long_term_goals ALTER COLUMN goal_id SET DEFAULT nextval('public.long_term_goals_goal_id_seq'::regclass);


--
-- Name: note_sync_ops id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_sync_ops ALTER COLUMN id SET DEFAULT nextval('public.note_sync_ops_id_seq'::regclass);


--
-- Name: schedule_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_rules ALTER COLUMN id SET DEFAULT nextval('public.schedule_rules_id_seq'::regclass);


--
-- Name: todo_list id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.todo_list ALTER COLUMN id SET DEFAULT nextval('public.todo_list_id_seq'::regclass);


--
-- Name: token_blocklist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blocklist ALTER COLUMN id SET DEFAULT nextval('public.token_blocklist_id_seq'::regclass);


--
-- Name: user_rule_assignment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_rule_assignment ALTER COLUMN id SET DEFAULT nextval('public.user_rule_assignment_id_seq'::regclass);


--
-- Name: agile_config agile_config_config_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agile_config
    ADD CONSTRAINT agile_config_config_key_key UNIQUE (config_key);


--
-- Name: agile_config agile_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agile_config
    ADD CONSTRAINT agile_config_pkey PRIMARY KEY (id);


--
-- Name: audit_item audit_item_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_item
    ADD CONSTRAINT audit_item_name_key UNIQUE (name);


--
-- Name: audit_item audit_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_item
    ADD CONSTRAINT audit_item_pkey PRIMARY KEY (id);


--
-- Name: audit_mark audit_mark_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_mark
    ADD CONSTRAINT audit_mark_pkey PRIMARY KEY (id);


--
-- Name: auth_codes auth_codes_code_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_codes
    ADD CONSTRAINT auth_codes_code_hash_key UNIQUE (code_hash);


--
-- Name: auth_codes auth_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_codes
    ADD CONSTRAINT auth_codes_pkey PRIMARY KEY (id);


--
-- Name: block_list block_list_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_list
    ADD CONSTRAINT block_list_pkey PRIMARY KEY (id);


--
-- Name: block_list block_list_qh_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_list
    ADD CONSTRAINT block_list_qh_key UNIQUE (qh);


--
-- Name: block_types block_types_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_types
    ADD CONSTRAINT block_types_name_key UNIQUE (name);


--
-- Name: block_types block_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.block_types
    ADD CONSTRAINT block_types_pkey PRIMARY KEY (id);


--
-- Name: users cons_username; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT cons_username UNIQUE (username);


--
-- Name: countdown_config countdown_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countdown_config
    ADD CONSTRAINT countdown_config_pkey PRIMARY KEY (id);


--
-- Name: countdown_config countdown_config_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countdown_config
    ADD CONSTRAINT countdown_config_user_id_key UNIQUE (user_id);


--
-- Name: filter_rule filter_rule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filter_rule
    ADD CONSTRAINT filter_rule_pkey PRIMARY KEY (qh);


--
-- Name: logs_daily logs_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_daily
    ADD CONSTRAINT logs_daily_pkey PRIMARY KEY (date, qh);


--
-- Name: logs logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs
    ADD CONSTRAINT logs_pkey PRIMARY KEY (id);


--
-- Name: long_term_goals_his long_term_goals_his_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.long_term_goals_his
    ADD CONSTRAINT long_term_goals_his_pkey PRIMARY KEY (goal_id);


--
-- Name: long_term_goals long_term_goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.long_term_goals
    ADD CONSTRAINT long_term_goals_pkey PRIMARY KEY (goal_id);


--
-- Name: media media_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media
    ADD CONSTRAINT media_pkey PRIMARY KEY (id);


--
-- Name: note_sync_ops note_sync_ops_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_sync_ops
    ADD CONSTRAINT note_sync_ops_pkey PRIMARY KEY (id);


--
-- Name: note_tags note_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_tags
    ADD CONSTRAINT note_tags_pkey PRIMARY KEY (note_id, tag_id);


--
-- Name: notes notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notes
    ADD CONSTRAINT notes_pkey PRIMARY KEY (id);


--
-- Name: schedule_rules schedule_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_rules
    ADD CONSTRAINT schedule_rules_pkey PRIMARY KEY (id);


--
-- Name: suspicious suspicious_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suspicious
    ADD CONSTRAINT suspicious_pkey PRIMARY KEY (date, qh);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: todo_list todo_list_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.todo_list
    ADD CONSTRAINT todo_list_pkey PRIMARY KEY (id);


--
-- Name: token_blocklist token_blocklist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blocklist
    ADD CONSTRAINT token_blocklist_pkey PRIMARY KEY (id);


--
-- Name: audit_mark uq_audit_mark_item_user_date; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_mark
    ADD CONSTRAINT uq_audit_mark_item_user_date UNIQUE (item_id, user_id, mark_date);


--
-- Name: note_sync_ops uq_notesync_user_op; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_sync_ops
    ADD CONSTRAINT uq_notesync_user_op UNIQUE (user_id, op_id);


--
-- Name: tags uq_tags_user_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT uq_tags_user_name UNIQUE (user_id, name);


--
-- Name: user_rule_assignment user_rule_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_rule_assignment
    ADD CONSTRAINT user_rule_assignment_pkey PRIMARY KEY (id);


--
-- Name: user_rule_assignment user_rule_assignment_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_rule_assignment
    ADD CONSTRAINT user_rule_assignment_user_id_key UNIQUE (user_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_audit_mark_user_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_mark_user_date ON public.audit_mark USING btree (user_id, mark_date);


--
-- Name: idx_logs_ip; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_logs_ip ON public.logs USING btree (ip);


--
-- Name: idx_qh; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qh ON public.logs USING btree (qh);


--
-- Name: idx_todo_list_username_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_todo_list_username_date ON public.todo_list USING btree (username, date);


--
-- Name: idx_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_username ON public.users USING btree (username) WITH (fillfactor='100', deduplicate_items='true');


--
-- Name: ix_auth_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_codes_user_id ON public.auth_codes USING btree (user_id);


--
-- Name: ix_media_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_note_id ON public.media USING btree (note_id);


--
-- Name: ix_media_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_media_user_id ON public.media USING btree (user_id);


--
-- Name: ix_note_sync_ops_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_sync_ops_note_id ON public.note_sync_ops USING btree (note_id);


--
-- Name: ix_note_sync_ops_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_note_sync_ops_user_id ON public.note_sync_ops USING btree (user_id);


--
-- Name: ix_notes_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notes_updated_at ON public.notes USING btree (updated_at);


--
-- Name: ix_notes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notes_user_id ON public.notes USING btree (user_id);


--
-- Name: ix_tags_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tags_user_id ON public.tags USING btree (user_id);


--
-- Name: ix_token_blocklist_jti; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_token_blocklist_jti ON public.token_blocklist USING btree (jti);


--
-- Name: audit_mark audit_mark_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_mark
    ADD CONSTRAINT audit_mark_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.audit_item(id) ON DELETE CASCADE;


--
-- Name: long_term_goals_his long_term_goals_his_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.long_term_goals_his
    ADD CONSTRAINT long_term_goals_his_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: long_term_goals long_term_goals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.long_term_goals
    ADD CONSTRAINT long_term_goals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: media media_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media
    ADD CONSTRAINT media_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id) ON DELETE CASCADE;


--
-- Name: note_tags note_tags_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_tags
    ADD CONSTRAINT note_tags_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id) ON DELETE CASCADE;


--
-- Name: note_tags note_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_tags
    ADD CONSTRAINT note_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: todo_list todo_list_username_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.todo_list
    ADD CONSTRAINT todo_list_username_fkey FOREIGN KEY (username) REFERENCES public.users(username) ON DELETE CASCADE;


--
-- Name: user_rule_assignment user_rule_assignment_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_rule_assignment
    ADD CONSTRAINT user_rule_assignment_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


