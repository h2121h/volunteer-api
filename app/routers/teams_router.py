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


@router.post("/create")
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
