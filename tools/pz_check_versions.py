#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Проверка актуальности модов Project Zomboid (Workshop) и версии Dedicated Server.

Что делает:
- Читает Zomboid\\Server\\servertest.ini, парсит WorkshopItems=...
- Для каждого Workshop ID:
	- Ищет локальные mod.info: serverfiles\\steamapps\\workshop\\content\\108600\\<id>\\mods\\*\\mod.info
	- Пытается вытащить версию из mod.info (если поле есть)
	- Запрашивает актуальные данные о моде из Steam (GetPublishedFileDetails)
- Проверяет версию сервера:
	- Локально: serverfiles\\steamapps\\appmanifest_380870.acf (buildid/LastUpdated)
	- Удалённо: steamcmd +app_info_print 380870 (buildid public ветки)
- Пишет лог рядом со скриптом

Запуск:
python pz_check_versions.py

Переопределение путей:
python pz_check_versions.py --ini "Zomboid\\Server\\servertest.ini" --steamapps "serverfiles\\steamapps" --steamcmd ".\\.\\bin\\steamcmd\\steamcmd.exe"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


WORKSHOP_APP_ID = 108600  # Workshop/контент Project Zomboid
SERVER_APP_ID = 380870  # Project Zomboid Dedicated Server


@dataclass
class ModLocalInfo:
	"""Локальная информация о моде из папки workshop."""
	workshop_id: str
	mod_dir: Path
	mod_info_path: Optional[Path]
	local_version: Optional[str]
	local_mtime: Optional[int]


@dataclass
class ModRemoteInfo:
	"""Удалённая информация о моде из Steam PublishedFileDetails."""
	workshop_id: str
	title: Optional[str]
	time_updated: Optional[int]
	consumer_app_id: Optional[int]
	result: Optional[int]


def _now_str() -> str:
	"""Текущее время для логов."""
	return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_log_line(log_path: Path, line: str) -> None:
	"""Дописать строку в лог."""
	log_path.parent.mkdir(parents=True, exist_ok=True)
	with log_path.open("a", encoding="utf-8") as f:
		f.write(line.rstrip() + "\n")


def _read_text_file(path: Path) -> str:
	"""Чтение файла с мягкой обработкой кодировок."""
	try:
		return path.read_text(encoding="utf-8", errors="replace")
	except Exception:
		return path.read_text(encoding="cp1251", errors="replace")


def parse_workshop_ids_from_ini(ini_path: Path) -> List[str]:
	"""
	Парсит WorkshopItems=... из servertest.ini.

	Возвращает уникальный список ID с сохранением порядка.
	"""
	if not ini_path.exists():
		raise FileNotFoundError(f"INI не найден: {ini_path}")

	content = _read_text_file(ini_path)

	m = re.search(r"(?im)^\s*WorkshopItems\s*=\s*(.+?)\s*$", content)
	if not m:
		return []

	raw = m.group(1).strip()
	parts = [p.strip() for p in raw.split(";") if p.strip()]

	seen = set()
	out: List[str] = []
	for p in parts:
		if p.isdigit() and p not in seen:
			seen.add(p)
			out.append(p)

	return out


def parse_version_from_mod_info(mod_info_text: str) -> Optional[str]:
	"""
	Пытается вытащить версию из mod.info.

	Многие моды не хранят версию явно.
	Пробуем типовые ключи.
	"""
	patterns = [
		r"(?im)^\s*version\s*=\s*(.+?)\s*$",
		r"(?im)^\s*modversion\s*=\s*(.+?)\s*$",
		r"(?im)^\s*workshopversion\s*=\s*(.+?)\s*$",
		r"(?im)^\s*build\s*=\s*(.+?)\s*$",
	]
	for pat in patterns:
		m = re.search(pat, mod_info_text)
		if m:
			val = m.group(1).strip().strip('"').strip("'")
			return val if val else None
	return None


def find_local_mod_infos(steamapps_dir: Path, workshop_id: str) -> List[ModLocalInfo]:
	"""
	Ищет локальные mod.info для конкретного Workshop ID.
	Возвращает список, потому что в mods\\ может быть несколько модов.
	"""
	base = steamapps_dir / "workshop" / "content" / str(WORKSHOP_APP_ID) / workshop_id
	mods_dir = base / "mods"

	out: List[ModLocalInfo] = []

	if not mods_dir.exists():
		out.append(ModLocalInfo(
			workshop_id=workshop_id,
			mod_dir=base,
			mod_info_path=None,
			local_version=None,
			local_mtime=None
		))
		return out

	for mod_folder in sorted([p for p in mods_dir.iterdir() if p.is_dir()]):
		mod_info = mod_folder / "mod.info"
		if mod_info.exists():
			text = _read_text_file(mod_info)
			local_ver = parse_version_from_mod_info(text)
			mtime = int(mod_info.stat().st_mtime)
			out.append(ModLocalInfo(
				workshop_id=workshop_id,
				mod_dir=mod_folder,
				mod_info_path=mod_info,
				local_version=local_ver,
				local_mtime=mtime
			))
		else:
			mtime = int(mod_folder.stat().st_mtime)
			out.append(ModLocalInfo(
				workshop_id=workshop_id,
				mod_dir=mod_folder,
				mod_info_path=None,
				local_version=None,
				local_mtime=mtime
			))

	if not out:
		out.append(ModLocalInfo(
			workshop_id=workshop_id,
			mod_dir=base,
			mod_info_path=None,
			local_version=None,
			local_mtime=None
		))

	return out


def _urlencode(s: str) -> str:
	"""URL encode для form-urlencoded."""
	from urllib.parse import quote_plus
	return quote_plus(str(s))


def steam_get_published_file_details(workshop_ids: List[str], timeout: int = 25) -> Dict[str, ModRemoteInfo]:
	"""
	Запрашивает PublishedFileDetails у Steam для списка Workshop ID (без ключа).
	Возвращает wid -> ModRemoteInfo.
	"""
	if not workshop_ids:
		return {}

	url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

	form_pairs = [("itemcount", str(len(workshop_ids)))]
	for i, wid in enumerate(workshop_ids):
		form_pairs.append((f"publishedfileids[{i}]", wid))

	data = "&".join([f"{_urlencode(k)}={_urlencode(v)}" for k, v in form_pairs]).encode("utf-8")

	req = urllib.request.Request(url, data=data, method="POST")
	req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")

	with urllib.request.urlopen(req, timeout=timeout) as resp:
		raw = resp.read().decode("utf-8", errors="replace")
		payload = json.loads(raw)

	out: Dict[str, ModRemoteInfo] = {}
	items = payload.get("response", {}).get("publishedfiledetails", [])
	for item in items:
		wid = str(item.get("publishedfileid", "")).strip()
		if not wid:
			continue

		result = int(item.get("result", 0) or 0)
		if result != 1:
			out[wid] = ModRemoteInfo(
				workshop_id=wid,
				title=None,
				time_updated=None,
				consumer_app_id=None,
				result=result
			)
			continue

		out[wid] = ModRemoteInfo(
			workshop_id=wid,
			title=item.get("title"),
			time_updated=int(item.get("time_updated") or 0) or None,
			consumer_app_id=int(item.get("consumer_app_id") or 0) or None,
			result=result
		)

	return out


def parse_appmanifest_build_info(appmanifest_path: Path) -> Tuple[Optional[str], Optional[int]]:
	"""
	Парсит appmanifest_*.acf.

	Возвращает (buildid, LastUpdated).
	"""
	if not appmanifest_path.exists():
		return None, None

	text = _read_text_file(appmanifest_path)

	buildid = None
	lastupdated = None

	mb = re.search(r'(?m)^\s*"buildid"\s*"(\d+)"\s*$', text)
	if mb:
		buildid = mb.group(1)

	ml = re.search(r'(?m)^\s*"LastUpdated"\s*"(\d+)"\s*$', text)
	if ml:
		lastupdated = int(ml.group(1))

	return buildid, lastupdated


def _extract_named_block(text: str, name: str) -> Optional[str]:
	"""
	Вырезает VDF-подобный блок по имени ("branches", "public", "unstable" и т.д.).
	Работает по принципу: находим "name", затем первый '{' и балансируем скобки.
	"""
	pos = text.find(f'"{name}"')
	if pos == -1:
		return None

	start = text.find("{", pos)
	if start == -1:
		return None

	depth = 0
	for i in range(start, len(text)):
		ch = text[i]
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				return text[start:i + 1]

	return None


def _extract_branch_block(text: str, branch_name: str) -> Optional[str]:
	"""
	Пытается аккуратно вытащить блок конкретной ветки из блока "branches".
	"""
	branches_block = _extract_named_block(text, "branches")
	if not branches_block:
		return None

	# Ищем ветку внутри branches
	pos = branches_block.find(f'"{branch_name}"')
	if pos == -1:
		return None

	start = branches_block.find("{", pos)
	if start == -1:
		return None

	depth = 0
	for i in range(start, len(branches_block)):
		ch = branches_block[i]
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				return branches_block[start:i + 1]

	return None


def steamcmd_get_buildid(steamcmd_path: Path, app_id: int, branch: str = "public", timeout: int = 180) -> Tuple[Optional[str], Optional[Path]]:
	"""
	Через steamcmd вытаскивает buildid указанной ветки для app_id.

	Всегда пытается сохранить полный вывод steamcmd в dump-файл рядом со скриптом.
	Если steamcmd не запускается, возвращает (None, dump_path) и пишет причину в dump.
	"""
	script_dir = Path(__file__).resolve().parent
	dump_path = script_dir / f"steamcmd_appinfo_{app_id}.txt"

	# Нормализуем путь (особенно важно на Windows при относительных путях)
	steamcmd_path = steamcmd_path.resolve()

	if not steamcmd_path.exists():
		try:
			dump_path.write_text(f"steamcmd.exe не найден по пути: {steamcmd_path}\n", encoding="utf-8", errors="replace")
		except Exception:
			pass
		return None, dump_path

	cmd = [
		str(steamcmd_path),
		"+login", "anonymous",
		"+app_info_update", "1",
		"+app_info_print", str(app_id),
		"+quit"
	]

	try:
		p = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=timeout,
			encoding="utf-8",
			errors="replace"
		)
	except Exception as e:
		try:
			dump_path.write_text(f"Ошибка запуска steamcmd: {e}\nКоманда: {' '.join(cmd)}\n", encoding="utf-8", errors="replace")
		except Exception:
			pass
		return None, dump_path

	out = (p.stdout or "") + "\n" + (p.stderr or "")

	# Пишем dump ВСЕГДА, даже если steamcmd вернул ошибку
	try:
		dump_path.write_text(
			f"ReturnCode: {p.returncode}\nCommand: {' '.join(cmd)}\n\n{out}",
			encoding="utf-8",
			errors="replace"
		)
	except Exception:
		# Если не смогли записать, хотя бы не падаем
		pass

	# Парсим нужную ветку
	branch_block = _extract_branch_block(out, branch_name=branch)
	if branch_block:
		m = re.search(r'(?im)^\s*"buildid"\s*"(\d+)"\s*$', branch_block)
		if m:
			return m.group(1), dump_path

	# Fallback: ищем buildid хоть где-то (чтобы понять, что данные вообще есть)
	m_any = re.search(r'(?im)^\s*"buildid"\s*"(\d+)"\s*$', out)
	if m_any:
		return m_any.group(1), dump_path

	return None, dump_path

def fmt_ts(ts: Optional[int]) -> str:
	"""Форматирует unix timestamp."""
	if not ts:
		return "—"
	try:
		return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
	except Exception:
		return str(ts)


def main() -> int:
	script_dir = Path(__file__).resolve().parent

	parser = argparse.ArgumentParser()
	parser.add_argument("--ini", default=r"Zomboid\Server\servertest.ini", help="Путь к servertest.ini")
	parser.add_argument("--steamapps", default=r"serverfiles\steamapps", help="Путь к serverfiles\\steamapps")
	parser.add_argument("--steamcmd", default=r".\.\bin\steamcmd\steamcmd.exe", help="Путь к steamcmd.exe")
	args = parser.parse_args()

	ini_path = Path(args.ini)
	steamapps_dir = Path(args.steamapps)
	steamcmd_path = Path(args.steamcmd)
	steamcmd_path = steamcmd_path.resolve()

	log_path = script_dir / "pz_versions.log"

	_write_log_line(log_path, "")
	_write_log_line(log_path, f"[{_now_str()}] Старт проверки")
	_write_log_line(log_path, f"INI: {ini_path}")
	_write_log_line(log_path, f"Steamapps: {steamapps_dir}")
	_write_log_line(log_path, f"SteamCMD: {steamcmd_path}")
	_write_log_line(log_path, "-" * 90)

	try:
		workshop_ids = parse_workshop_ids_from_ini(ini_path)
	except Exception as e:
		_write_log_line(log_path, f"ОШИБКА: не удалось прочитать/распарсить ini: {e}")
		return 1

	if not workshop_ids:
		_write_log_line(log_path, "WorkshopItems не найден или пуст.")
		_write_log_line(log_path, f"[{_now_str()}] Готово. Лог: {log_path}")
		return 0

	_write_log_line(log_path, f"Найдено Workshop ID: {len(workshop_ids)}")
	_write_log_line(log_path, f"Порядок ID: {', '.join(workshop_ids)}")

	_write_log_line(log_path, "-" * 90)
	_write_log_line(log_path, "Получение удалённых данных по модам из Steam (PublishedFileDetails)...")

	remote_map: Dict[str, ModRemoteInfo] = {}
	try:
		remote_map = steam_get_published_file_details(workshop_ids)
		_write_log_line(log_path, f"Steam ответил по модам: {len(remote_map)}")
	except Exception as e:
		_write_log_line(log_path, f"ОШИБКА: не удалось получить PublishedFileDetails: {e}")

	_write_log_line(log_path, "-" * 90)
	_write_log_line(log_path, "Сравнение локальных модов с Steam:")

	for wid in workshop_ids:
		_write_log_line(log_path, "")
		_write_log_line(log_path, f"[MOD {wid}]")

		remote = remote_map.get(wid)
		if remote:
			_write_log_line(log_path, f"Steam result: {remote.result}")
			_write_log_line(log_path, f"Steam title: {remote.title or '—'}")
			_write_log_line(log_path, f"Steam time_updated: {fmt_ts(remote.time_updated)}")
			_write_log_line(log_path, f"Steam consumer_app_id: {remote.consumer_app_id or '—'}")
		else:
			_write_log_line(log_path, "Steam данные: — (нет ответа/ошибка)")

		local_infos = find_local_mod_infos(steamapps_dir, wid)
		for li in local_infos:
			_write_log_line(log_path, f"Локальный мод каталог: {li.mod_dir}")
			_write_log_line(log_path, f"mod.info: {li.mod_info_path or '—'}")
			_write_log_line(log_path, f"Локальная версия (из mod.info): {li.local_version or '—'}")
			_write_log_line(log_path, f"Локальная дата (mtime): {fmt_ts(li.local_mtime)}")

			if remote and remote.time_updated and li.local_mtime:
				if li.local_mtime >= remote.time_updated:
					_write_log_line(log_path, "Сравнение: OK (локально не старее Steam по времени)")
				else:
					_write_log_line(log_path, "Сравнение: НУЖНО ОБНОВИТЬ (локально старее Steam по времени)")
			else:
				_write_log_line(log_path, "Сравнение: пропущено (нет времени Steam или локального mtime)")

	_write_log_line(log_path, "-" * 90)
	_write_log_line(log_path, "Проверка версии Dedicated Server:")

	appmanifest_path = steamapps_dir / f"appmanifest_{SERVER_APP_ID}.acf"
	local_buildid, local_lastupdated = parse_appmanifest_build_info(appmanifest_path)

	_write_log_line(log_path, f"Локальный appmanifest: {appmanifest_path}")
	_write_log_line(log_path, f"Локальный buildid: {local_buildid or '—'}")
	_write_log_line(log_path, f"Локальный LastUpdated: {fmt_ts(local_lastupdated)}")

	_write_log_line(log_path, "")
	_write_log_line(log_path, "Получение актуального buildid через steamcmd...")

	branch_name = "unstable"

	remote_buildid, dump_path = steamcmd_get_buildid(steamcmd_path, SERVER_APP_ID, branch=branch_name)

	_write_log_line(log_path, f"Steam buildid ({branch_name}): {remote_buildid or '—'}")
	_write_log_line(log_path, f"Steamcmd dump: {dump_path or '—'}")

	if local_buildid and remote_buildid:
		if local_buildid == remote_buildid:
			_write_log_line(log_path, "Сервер: OK (buildid совпадает)")
		else:
			_write_log_line(log_path, "Сервер: НУЖНО ОБНОВИТЬ (buildid отличается)")
	else:
		_write_log_line(log_path, "Сервер: сравнение пропущено (не удалось получить buildid локально или через steamcmd)")

	_write_log_line(log_path, "-" * 90)
	_write_log_line(log_path, f"[{_now_str()}] Готово. Лог: {log_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
