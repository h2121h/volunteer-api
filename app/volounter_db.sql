
CREATE TABLE roles (
    id          SMALLSERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,  
    name        VARCHAR(100) NOT NULL
);

INSERT INTO roles (code, name) VALUES
('volunteer',   'Волонтёр'),
('coordinator', 'Координатор волонтёров'),
('manager',     'Менеджер социальных проектов'),
('admin',       'Администратор системы'),
('it_support',  'IT-специалист');



CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(180) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(120) NOT NULL,
    phone           VARCHAR(30),
    city            VARCHAR(100),
    role_id         SMALLINT REFERENCES roles(id),
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);



CREATE TABLE logins (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    email       VARCHAR(180),
    ip          INET,
    user_agent  TEXT,
    success     BOOLEAN NOT NULL,
    reason      VARCHAR(80),           
    happened_at TIMESTAMPTZ DEFAULT NOW()
);



CREATE TABLE volunteer_documents (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    doc_type        VARCHAR(80) NOT NULL,      
    file_url        TEXT NOT NULL,
    status          VARCHAR(20) DEFAULT 'new', 
    uploaded_at     TIMESTAMPTZ DEFAULT NOW(),
    verified_at     TIMESTAMPTZ,
    verified_by     BIGINT REFERENCES users(id)
);



CREATE TABLE projects (
    id              BIGSERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    status          VARCHAR(20) DEFAULT 'active', 
    created_by      BIGINT REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);



CREATE TABLE tasks (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    title           VARCHAR(180) NOT NULL,
    description     TEXT,
    event_date      DATE NOT NULL,
    location        VARCHAR(150),
    needed_people   SMALLINT DEFAULT 5,
    status          VARCHAR(20) DEFAULT 'open'    
);



CREATE TABLE task_applications (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
    status      VARCHAR(20) DEFAULT 'pending', 
    message     TEXT,
    applied_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(task_id, user_id)
);



CREATE TABLE task_assignments (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    user_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_by BIGINT REFERENCES users(id),
    status      VARCHAR(20) DEFAULT 'assigned' 
);


CREATE TABLE task_reports (
    id              BIGSERIAL PRIMARY KEY,
    assignment_id   BIGINT REFERENCES task_assignments(id) ON DELETE CASCADE,
    user_id         BIGINT REFERENCES users(id),
    hours           NUMERIC(5,2),
    comment         TEXT,
    photo_url       TEXT,
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),
    is_approved     BOOLEAN DEFAULT FALSE
);



CREATE TABLE project_feedback (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    user_id     BIGINT REFERENCES users(id),
    rating      SMALLINT CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);



CREATE TABLE skills (
    id   SMALLSERIAL PRIMARY KEY,
    name VARCHAR(80) UNIQUE NOT NULL
);

CREATE TABLE user_skills (
    user_id  BIGINT   REFERENCES users(id) ON DELETE CASCADE,
    skill_id SMALLINT REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, skill_id)
);



CREATE TABLE backups (
    id          BIGSERIAL PRIMARY KEY,
    performed_by BIGINT REFERENCES users(id),
    backup_date  TIMESTAMPTZ DEFAULT NOW(),
    file_path    TEXT,
    size_mb      INTEGER,
    status       VARCHAR(20) DEFAULT 'success' 
);

CREATE TABLE registration (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(180) UNIQUE NOT NULL,
    token       VARCHAR(100),              
    status      VARCHAR(20) DEFAULT 'new', 
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    user_id     BIGINT                      
);

CREATE INDEX idx_users_role        ON users(role_id);
CREATE INDEX idx_logins_email      ON logins(email, happened_at DESC);
CREATE INDEX idx_tasks_date        ON tasks(event_date);
CREATE INDEX idx_applications_task ON task_applications(task_id, status);
CREATE INDEX idx_assignments_task  ON task_assignments(task_id);
CREATE INDEX idx_reports_assignment ON task_reports(assignment_id);
