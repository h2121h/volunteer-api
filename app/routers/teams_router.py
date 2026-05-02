from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from app import models, auth
from app.database import get_db
from app.logger import logger

router = APIRouter(prefix="/api/teams", tags=["Teams"])


class TeamBody(BaseModel):
    name:        str
    description: Optional[str] = ""
    task_id:     Optional[int] = None
    max_size:    Optional[int] = None


def _ensure_tables(db: Session):
    """Создаём таблицы если не существуют."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS teams (
                id          BIGSERIAL PRIMARY KEY,
                name        VARCHAR(100) NOT NULL,
                description TEXT,
                task_id     BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
                max_size    SMALLINT,
                created_by  BIGINT REFERENCES users(id),
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS team_members (
                team_id   BIGINT REFERENCES teams(id) ON DELETE CASCADE,
                user_id   BIGINT REFERENCES users(id) ON DELETE CASCADE,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, user_id)
            );
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[TEAMS] ensure_tables: {e}")


@router.get("/available")
def get_available_teams(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.volunteer_required),
):
    """Все команды для волонтёра — с флагом is_member."""
    _ensure_tables(db)
    try:
        rows = db.execute(text("""
            SELECT
                t.id, t.name, t.description, t.task_id, t.max_size,
                tk.title   AS task_title,
                u.name     AS curator_name,
                COUNT(tm.user_id) AS members_count,
                MAX(CASE WHEN tm.user_id = :uid THEN 1 ELSE 0 END) AS is_member
            FROM teams t
            LEFT JOIN tasks       tk ON tk.id = t.task_id
            LEFT JOIN users       u  ON u.id  = t.created_by
            LEFT JOIN team_members tm ON tm.team_id = t.id
            GROUP BY t.id, t.name, t.description, t.task_id, t.max_size,
                     tk.title, u.name
            ORDER BY t.id DESC
        """), {"uid": user.id}).fetchall()

        return [
            {
                "id":            r[0],
                "name":          r[1] or "",
                "description":   r[2] or "",
                "task_id":       r[3],
                "max_size":      r[4],
                "task_title":    r[5] or "",
                "curator_name":  r[6] or "",
                "members_count": int(r[7] or 0),
                "is_member":     bool(r[8]),
            }
            for r in rows
        ]
    except Exception as e:
        db.rollback()
        logger.warning(f"[TEAMS] available: {e}")
        return []


@router.get("/my")
def get_my_teams(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.volunteer_required),
):
    """Команды волонтёра с проектами и задачами."""
    _ensure_tables(db)
    try:
        rows = db.execute(text("""
            SELECT
                t.id        AS team_id,
                t.name      AS team_name,
                t.task_id,
                tk.title    AS task_title,
                tk.status   AS task_status,
                tk.event_date::text AS task_date,
                tk.location AS task_location,
                p.id        AS project_id,
                p.title     AS project_title,
                COUNT(tm2.user_id) AS members_count
            FROM team_members tm
            JOIN teams t         ON t.id = tm.team_id
            LEFT JOIN tasks tk   ON tk.id = t.task_id
            LEFT JOIN projects p ON p.id = tk.project_id
            LEFT JOIN team_members tm2 ON tm2.team_id = t.id
            WHERE tm.user_id = :uid
            GROUP BY t.id, t.name, t.task_id, tk.title, tk.status,
                     tk.event_date, tk.location, p.id, p.title
            ORDER BY t.id DESC
        """), {"uid": user.id}).fetchall()

        return [
            {
                "team_id":       r[0],
                "team_name":     r[1] or "",
                "task_id":       r[2],
                "task_title":    r[3] or "",
                "task_status":   r[4] or "",
                "task_date":     r[5] or "",
                "task_location": r[6] or "",
                "project_id":    r[7],
                "project_title": r[8] or "",
                "members_count": int(r[9] or 0),
            }
            for r in rows
        ]
    except Exception as e:
        db.rollback()
        logger.warning(f"[TEAMS] my: {e}")
        return []


@router.post("/{team_id}/join")
def join_team(
    team_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.volunteer_required),
):
    """Вступить в команду. Волонтёр может состоять только в одной команде."""
    _ensure_tables(db)
    try:
        # Проверяем что волонтёр ещё не в какой-то команде
        existing = db.execute(text(
            "SELECT t.id, t.name FROM team_members tm "
            "JOIN teams t ON t.id = tm.team_id "
            "WHERE tm.user_id = :uid LIMIT 1"
        ), {"uid": user.id}).fetchone()
        if existing:
            if existing[0] == team_id:
                return {"success": False, "message": "Вы уже в этой команде"}
            return {
                "success": False,
                "message": f"Вы уже состоите в команде «{existing[1]}». Сначала выйдите из неё."
            }

        # Проверяем лимит команды
        row = db.execute(text(
            "SELECT max_size, COUNT(tm.user_id) AS cnt FROM teams t "
            "LEFT JOIN team_members tm ON tm.team_id = t.id "
            "WHERE t.id = :tid GROUP BY t.max_size"
        ), {"tid": team_id}).fetchone()
        if not row:
            return {"success": False, "message": "Команда не найдена"}
        if row[0] and int(row[1] or 0) >= row[0]:
            return {"success": False, "message": "Команда заполнена"}

        db.execute(text("""
            INSERT INTO team_members (team_id, user_id)
            VALUES (:tid, :uid) ON CONFLICT DO NOTHING
        """), {"tid": team_id, "uid": user.id})
        db.commit()
        return {"success": True, "message": "Вы вступили в команду!"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}


@router.post("/{team_id}/leave")
def leave_team(
    team_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.volunteer_required),
):
    """Выйти из команды."""
    try:
        db.execute(text(
            "DELETE FROM team_members WHERE team_id = :tid AND user_id = :uid"
        ), {"tid": team_id, "uid": user.id})
        db.commit()
        return {"success": True, "message": "Вы вышли из команды"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}


@router.patch("/{team_id}/set-task")
def set_team_task(
    team_id: int,
    body:    dict,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    """Привязать задачу к команде (куратор)."""
    task_id = body.get('task_id')
    try:
        db.execute(text(
            "UPDATE teams SET task_id = :tid WHERE id = :team_id"
        ), {"tid": task_id, "team_id": team_id})
        db.commit()
        return {"success": True, "message": f"Задача привязана к команде"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}


def create_team(
    body: TeamBody,
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.curator_required),
):
    _ensure_tables(db)
    try:
        row = db.execute(text("""
            INSERT INTO teams (name, description, task_id, max_size, created_by)
            VALUES (:name, :desc, :task_id, :max_size, :uid)
            RETURNING id
        """), {
            "name":     body.name,
            "desc":     body.description or "",
            "task_id":  body.task_id,
            "max_size": body.max_size,
            "uid":      user.id,
        }).fetchone()
        db.commit()
        return {"success": True, "id": row[0],
                "message": f"Команда «{body.name}» создана"}
    except Exception as e:
        db.rollback()
        logger.error(f"[TEAMS] create: {e}")
        raise HTTPException(500, str(e))


@router.get("")
def get_teams(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.curator_required),
):
    _ensure_tables(db)
    try:
        teams = db.execute(text("""
            SELECT t.id, t.name, t.description, t.task_id,
                   t.max_size, tk.title as task_title
            FROM teams t
            LEFT JOIN tasks tk ON tk.id = t.task_id
            WHERE t.created_by = :uid
            ORDER BY t.created_at DESC
        """), {"uid": user.id}).fetchall()

        result = []
        for team in teams:
            members = db.execute(text("""
                SELECT u.id, u.name, u.email
                FROM team_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.team_id = :tid
            """), {"tid": team[0]}).fetchall()

            result.append({
                "id":          team[0],
                "name":        team[1] or "",
                "description": team[2] or "",
                "task_id":     team[3],
                "max_size":    team[4],
                "task_title":  team[5],
                "members": [
                    {"id": m[0], "name": m[1] or m[2], "email": m[2]}
                    for m in members
                ],
            })
        return result
    except Exception as e:
        db.rollback()
        logger.warning(f"[TEAMS] get: {e}")
        return []


@router.post("/{team_id}/members")
def add_member(
    team_id: int,
    body:    dict,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    try:
        db.execute(text("""
            INSERT INTO team_members (team_id, user_id)
            VALUES (:tid, :uid)
            ON CONFLICT DO NOTHING
        """), {"tid": team_id, "uid": body.get("user_id")})
        db.commit()
        return {"success": True, "message": "Волонтёр добавлен"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))


@router.delete("/{team_id}/members/{user_id}")
def remove_member(
    team_id: int,
    user_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    try:
        db.execute(text("""
            DELETE FROM team_members
            WHERE team_id = :tid AND user_id = :uid
        """), {"tid": team_id, "uid": user_id})
        db.commit()
        return {"success": True, "message": "Участник удалён"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))


@router.delete("/{team_id}")
def delete_team(
    team_id: int,
    db:      Session = Depends(get_db),
    user:    models.User = Depends(auth.curator_required),
):
    try:
        db.execute(text(
            "DELETE FROM teams WHERE id = :id AND created_by = :uid"),
            {"id": team_id, "uid": user.id})
        db.commit()
        return {"success": True, "message": "Команда удалена"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
