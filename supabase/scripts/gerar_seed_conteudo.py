"""Gera a migração de conteúdo do curso a partir de education_content.py e dos MP4 em media/education.

Uso (na pasta FinTrack-0.6.1):
    .venv\\Scripts\\python.exe supabase\\scripts\\gerar_seed_conteudo.py

Os UUIDs são determinísticos (uuid5), então rodar de novo gera o mesmo arquivo e a migração de dados
consegue mapear chaves antigas (módulo:aula) para os novos ids sem consultar o banco.
"""
import hashlib
import json
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import education_content as ec  # noqa: E402
import video_lessons  # noqa: E402

NS = uuid.UUID("6f1d3c2a-6a43-4f43-9a0e-0f1a7c5e2b10")
OUT = BASE / "supabase" / "migrations" / "20261117133330_conteudo_do_curso.sql"
VIDEO_VERSION = "1"


def uid(*parts):
    return str(uuid.uuid5(NS, ":".join(parts)))


def q(value):
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def j(value):
    return q(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def public_data(a):
    t = a["t"]
    if t in ("quiz", "multi"):
        return {"opts": a["opts"]}
    if t == "classify":
        return {"buckets": a["buckets"], "items": [i[0] for i in a["items"]]}
    if t == "calc":
        return {"unit": a["unit"]}
    if t == "budget":
        return {"cats": a["cats"], "total": a["total"]}
    raise ValueError(t)


def answer_and_expected(a):
    t = a["t"]
    if t == "quiz":
        return a["ans"], ec.grade_item(a, a["ans"])[1]
    if t == "multi":
        return sorted(a["ans"]), ec.grade_item(a, a["ans"])[1]
    if t == "classify":
        right = [it[1] for it in a["items"]]
        return right, ec.grade_item(a, right)[1]
    if t == "calc":
        return a["ans"], ec.grade_item(a, a["ans"])[1]
    if t == "budget":
        return a["rules"], a["right"]
    raise ValueError(t)


def main():
    lines = ["-- FinTrack · 0011 · Conteúdo do curso (GERADO por supabase/scripts/gerar_seed_conteudo.py — não edite à mão).",
             f"-- Fonte: education_content.py (revisão {ec.REVIEWED}); nota mínima {ec.PASS}%.",
             "-- Dados globais reais: 4 módulos, 12 aulas, atividades, gabaritos (schema private) e 4 vídeos introdutórios.",
             "", f"update private.app_settings set value = '{ec.PASS}' where key = 'education_pass_percent';", ""]
    reviewed = ec.REVIEWED + "-01"
    for mpos, m in enumerate(ec.EDUCATION, start=1):
        mid = uid("module", m["key"])
        lines.append(
            "insert into public.education_modules (id, key, title, level, level_name, description, position, status) values "
            f"({q(mid)}, {q(m['key'])}, {q(m['title'])}, {m['level']}, {q(m['level_name'])}, {q(m['description'])}, {mpos}, 'publicado') "
            "on conflict (key) do update set title = excluded.title, level = excluded.level, level_name = excluded.level_name, "
            "description = excluded.description, position = excluded.position;")
        for lpos, t in enumerate(m["topics"], start=1):
            lid = uid("lesson", m["key"], t["key"])
            lines.append(
                "insert into public.education_lessons (id, module_id, key, title, position, status) values "
                f"({q(lid)}, {q(mid)}, {q(t['key'])}, {q(t['title'])}, {lpos}, 'publicado') "
                "on conflict (module_id, key) do update set title = excluded.title, position = excluded.position;")
            summary = "array[" + ", ".join(q(s) for s in t["summary"]) + "]::text[]"
            lines.append(
                "insert into public.education_lesson_contents (lesson_id, goal, explanation, example, summary, sources, reviewed_on) values "
                f"({q(lid)}, {q(t['goal'])}, {q(t['explain'])}, {q(t['example'])}, {summary}, {j(t['sources'])}, {q(reviewed)}) "
                "on conflict (lesson_id) do update set goal = excluded.goal, explanation = excluded.explanation, example = excluded.example, "
                "summary = excluded.summary, sources = excluded.sources, reviewed_on = excluded.reviewed_on;")
            for apos, a in enumerate(t["acts"]):
                aid = uid("activity", m["key"], t["key"], str(apos))
                answer, expected = answer_and_expected(a)
                lines.append(
                    "insert into public.education_activities (id, lesson_id, position, kind, prompt, public_data) values "
                    f"({q(aid)}, {q(lid)}, {apos}, {q(a['t'])}, {q(a['q'])}, {j(public_data(a))}) "
                    "on conflict (lesson_id, position) do update set kind = excluded.kind, prompt = excluded.prompt, public_data = excluded.public_data;")
                lines.append(
                    "insert into private.education_answer_keys (activity_id, answer, expected_text, explanation) values "
                    f"({q(aid)}, {j(answer)}, {q(expected)}, {q(a['why'])}) "
                    "on conflict (activity_id) do update set answer = excluded.answer, expected_text = excluded.expected_text, explanation = excluded.explanation;")
        video = video_lessons.MEDIA / (m["key"] + ".mp4")
        if video.exists():
            data = video.read_bytes()
            lines.append(
                "insert into public.education_video_assets (id, module_id, version, storage_bucket, storage_path, duration_seconds, size_bytes, sha256, status, published_at) values "
                f"({q(uid('video', m['key'], VIDEO_VERSION))}, {q(mid)}, {q(VIDEO_VERSION)}, 'education-videos', {q('intro/' + m['key'] + '-v' + VIDEO_VERSION + '.mp4')}, "
                f"{video_lessons.VIDEOS[m['key']]['duration']}, {len(data)}, {q(hashlib.sha256(data).hexdigest())}, 'publicado', now()) "
                "on conflict (module_id, version) do nothing;")
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Gerado {OUT.relative_to(BASE)}")


def update_migration(out: Path):
    """Migração de ATUALIZAÇÃO do conteúdo (aulas, atividades e gabaritos), compacta e idempotente.
    Atividades além do novo total de cada aula são apagadas (o gabarito vai junto, em cascata)."""
    reviewed = ec.REVIEWED + "-01"
    contents, acts, keys, counts = [], [], [], []
    for m in ec.EDUCATION:
        for t in m["topics"]:
            lid = uid("lesson", m["key"], t["key"])
            summary = "array[" + ", ".join(q(s) for s in t["summary"]) + "]::text[]"
            contents.append(f"({q(lid)}, {q(t['goal'])}, {q(t['explain'])}, {q(t['example'])}, {summary}, {j(t['sources'])}, {q(reviewed)}::date)")
            counts.append(f"({q(lid)}::uuid, {len(t['acts'])})")
            for apos, a in enumerate(t["acts"]):
                aid = uid("activity", m["key"], t["key"], str(apos))
                answer, expected = answer_and_expected(a)
                acts.append(f"({q(aid)}::uuid, {q(lid)}::uuid, {apos}, {q(a['t'])}, {q(a['q'])}, {j(public_data(a))})")
                keys.append(f"({q(aid)}::uuid, {j(answer)}, {q(expected)}, {q(a['why'])})")
    sql = [f"-- FinTrack · atualização do conteúdo do curso (GERADO por gerar_seed_conteudo.py --atualizar). Revisão {ec.REVIEWED}.",
           "-- Dificuldade progressiva por módulo. Progresso e notas já salvos são mantidos.",
           "delete from public.education_activities a using (values " + ", ".join(counts) + ") n(lesson_id, total)",
           " where a.lesson_id = n.lesson_id and a.position >= n.total;",
           "insert into public.education_lesson_contents (lesson_id, goal, explanation, example, summary, sources, reviewed_on) values",
           ",\n".join(contents),
           "on conflict (lesson_id) do update set goal = excluded.goal, explanation = excluded.explanation, example = excluded.example,"
           " summary = excluded.summary, sources = excluded.sources, reviewed_on = excluded.reviewed_on;",
           "insert into public.education_activities (id, lesson_id, position, kind, prompt, public_data) values",
           ",\n".join(acts),
           "on conflict (lesson_id, position) do update set kind = excluded.kind, prompt = excluded.prompt, public_data = excluded.public_data;",
           "insert into private.education_answer_keys (activity_id, answer, expected_text, explanation) values",
           ",\n".join(keys),
           "on conflict (activity_id) do update set answer = excluded.answer, expected_text = excluded.expected_text, explanation = excluded.explanation;"]
    out.write_text("\n".join(sql) + "\n", encoding="utf-8")
    print(f"Gerado {out}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--atualizar":
        update_migration(Path(sys.argv[2]))
    else:
        main()
