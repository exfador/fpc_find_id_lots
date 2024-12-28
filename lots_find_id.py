from __future__ import annotations

from os.path import exists
from typing import TYPE_CHECKING

import telebot

if TYPE_CHECKING:
    from exfa import exfa

import FunPayAPI.types
from FunPayAPI.account import Account
from logging import getLogger
from telebot.types import Message
from tg_bot import static_keyboards as skb
import time
import json

NAME = "Автоматическое получение лотов по ID"
VERSION = "0.1"
DESCRIPTION = "Данный плагин позволяет автоматически получать лоты по их ID."
CREDITS = "@exfador"
UUID = "32811ab3-2474-466a-846e-5165d4f1c17b"
SETTINGS_PAGE = False

logger = getLogger("FPC.lots_find_id")
RUNNING = False



def init_commands(exfa: exfa):
    if not exfa.telegram:
        return
    tg = exfa.telegram
    bot = exfa.telegram.bot

    def get_current_account(tg_msg: Message) -> FunPayAPI.types.UserProfile:
        attempts = 3
        while attempts:
            try:
                profile = exfa.account.get_user(exfa.account.id)
                return profile
            except:
                logger.error("[АВТОЛОТЫ] Не удалось получить данные о текущем профиле.")
                logger.debug("TRACEBACK", exc_info=True)
                time.sleep(1)
                attempts -= 1
        else:
            bot.send_message(tg_msg.chat.id, "❌ Не удалось получить данные текущего профиля.")
            raise Exception

    def get_lots_info(tg_msg: Message, profile: FunPayAPI.types.UserProfile, subcategory_ids: list[int]) -> list[dict]:
        result = []
        for i in profile.get_lots():
            if i.subcategory.id not in subcategory_ids:
                continue
            
            if i.subcategory.type == FunPayAPI.types.SubCategoryTypes.CURRENCY:
                continue
            
            attempts = 3
            while attempts:
                try:
                    lot_fields = exfa.account.get_lot_fields(i.id)
                    fields = lot_fields.fields
                    
                    if "secrets" in fields.keys():
                        if not settings.get("with_secrets"):
                            fields["secrets"] = ""
                            del fields["auto_delivery"]
                    
                    lot_info = {
                        "id": i.id,
                        "description": i.description,
                        "category_id": i.subcategory.category.id,
                        "category_name": i.subcategory.category.name,
                        "subcategory_id": i.subcategory.id,
                        "subcategory_name": i.subcategory.name,
                        "fields": fields
                    }
                    
                    logger.info(f"[АВТОЛОТЫ] Лот {i.id} {i.description} принадлежит категории {i.subcategory.category.name} (ID: {i.subcategory.category.id}) и подкатегории {i.subcategory.name} (ID: {i.subcategory.id}).")
                    
                    result.append(lot_info)
                    logger.info(f"[АВТОЛОТЫ] Получены данные о лоте {i.id} {i.description}. Категория: {i.subcategory.category.name}, Подкатегория: {i.subcategory.name}")
                    break
                except Exception as e:
                    logger.error(f"[АВТОЛОТЫ] Не удалось получить данные о лоте {i.id} {i.description}.")
                    logger.debug("TRACEBACK", exc_info=True)
                    time.sleep(2)
                    attempts -= 1
            else:
                bot.send_message(tg_msg.chat.id, f"❌ Не удалось получить данные о <a href=\"https://funpay.com/lots/offer?id={i.id}\">лоте {i.id} {i.description}</a>. Пропускаю.")
                time.sleep(1)
                continue
            time.sleep(0.5)
        return result

    def lots_find_id(m: Message):
        global RUNNING
        if RUNNING:
            bot.send_message(m.chat.id, "❌ Процесс получения лотов уже начат! Дождитесь завершения текущего процесса или перезапустите бота.")
            return
        RUNNING = True
        try:
            bot.send_message(m.chat.id, f"Получаю данные о текущем профиле...")
            profile = get_current_account(m)

            settings_auto_path = "storage/plugins/settings_auto.json"
            if exists(settings_auto_path):
                with open(settings_auto_path, "r", encoding="utf-8") as f:
                    settings_auto = json.loads(f.read())
                    subcategory_ids = settings_auto.get("subcategory_ids", [])
            else:
                subcategory_ids = []

            if not subcategory_ids:
                bot.send_message(m.chat.id, "❌ Не удалось загрузить subcategory_ids из файла настроек. Создайте его в формате: <code>/set_subcategories 703, 732</code>, после чего повторите процесс.", parse_mode='HTML')
                RUNNING = False
                return

            result = []
            for i in get_lots_info(m, profile, subcategory_ids):
                fields = i["fields"]
                del fields["csrf_token"]
                del fields["offer_id"]
                result.append(fields)

            with open("storage/cache/lots.json", "w", encoding="utf-8") as f:
                f.write(json.dumps(result, indent=4, ensure_ascii=False))
            with open("storage/cache/lots.json", "r", encoding="utf-8") as f:
                bot.send_document(m.chat.id, f)

            auto_lots_path = "storage/cache/auto_lots.json"
            auto_lots_data = {
                "lot_mapping": {},
                "chat_id": 8171383326,
            }

            if exists(auto_lots_path):
                with open(auto_lots_path, "r", encoding="utf-8") as f:
                    auto_lots_data = json.loads(f.read())

            current_lots = auto_lots_data["lot_mapping"]

            for idx, lot in enumerate(result, start=1):
                lot_name = lot.get("fields[summary][ru]", "")
                service_id = 1 
                quantity = 1 

                if not any(lot_info["name"] == lot_name for lot_info in current_lots.values()):
                    new_lot_key = f"lot_{len(current_lots) + 1}"
                    current_lots[new_lot_key] = {
                        "name": lot_name,
                        "service_id": service_id,
                        "quantity": quantity
                    }

            auto_lots_data["lot_mapping"] = current_lots
            with open(auto_lots_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(auto_lots_data, indent=4, ensure_ascii=False))

            RUNNING = False
        except Exception as e:
            RUNNING = False
            logger.error("[АВТОЛОТЫ] Не удалось кэшировать лоты.")
            logger.debug("TRACEBACK", exc_info=True)
            bot.send_message(m.chat.id, f"❌ Не удалось кэшировать лоты. Ошибка: {str(e)}")
            return
        
    def set_subcategories(m: Message):
        try:
            text = m.text.strip().replace("/set_subcategories", "").strip()
            subcategory_ids = [int(id.strip()) for id in text.split(",") if id.strip().isdigit()]

            if not subcategory_ids:
                bot.send_message(m.chat.id, "❌ Неверный формат. Введите ID подкатегорий через запятую (например, 732, 704).")
                return

            settings_auto_path = "storage/plugins/settings_auto.json"
            settings_auto = {"subcategory_ids": subcategory_ids}
            with open(settings_auto_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(settings_auto, indent=4, ensure_ascii=False))

            bot.send_message(m.chat.id, f"🟢 Subcategory_ids успешно обновлены: {subcategory_ids}")
            logger.info(f"[АВТОЛОТЫ] Subcategory_ids обновлены: {subcategory_ids}")
        except Exception as e:
            logger.error("[АВТОЛОТЫ] Не удалось обновить subcategory_ids.")
            logger.debug("TRACEBACK", exc_info=True)
            bot.send_message(m.chat.id, f"❌ Не удалось обновить subcategory_ids. Ошибка: {str(e)}")

    def show_lots_ids(m: Message):
        settings_auto_path = "storage/plugins/settings_auto.json"
        if exists(settings_auto_path):
            with open(settings_auto_path, "r", encoding="utf-8") as f:
                settings_auto = json.loads(f.read())
                subcategory_ids = settings_auto.get("subcategory_ids", [])
                if subcategory_ids:
                    bot.send_message(m.chat.id, f"🟢 Текущие ID подкатегорий: <code>{', '.join(map(str, subcategory_ids))}</code>", parse_mode='HTML')
                else:
                    bot.send_message(m.chat.id, "🟡 Нет сохраненных ID подкатегорий.")
        else:
            bot.send_message(m.chat.id, "❌ Файл настроек не найден.")

    def delete_lots_ids(m: Message):
        try:
            text = m.text.strip().replace("/delete_lots_id", "").strip()
            ids_to_delete = [int(id.strip()) for id in text.split(",") if id.strip().isdigit()]

            if not ids_to_delete:
                bot.send_message(m.chat.id, "❌ Неверный формат. Введите ID подкатегорий через запятую (например, 732, 704).")
                return
            settings_auto_path = "storage/plugins/settings_auto.json"
            if exists(settings_auto_path):
                with open(settings_auto_path, "r", encoding="utf-8") as f:
                    settings_auto = json.loads(f.read())
                    subcategory_ids = settings_auto.get("subcategory_ids", [])
                subcategory_ids = [id for id in subcategory_ids if id not in ids_to_delete]

                settings_auto["subcategory_ids"] = subcategory_ids
                with open(settings_auto_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(settings_auto, indent=4, ensure_ascii=False))

                bot.send_message(m.chat.id, f"🟢 ID подкатегорий успешно удалены. Текущие ID: {', '.join(map(str, subcategory_ids))}")
                logger.info(f"[АВТОЛОТЫ] ID подкатегорий удалены: {ids_to_delete}")
            else:
                bot.send_message(m.chat.id, "❌ Файл настроек не найден.")
        except Exception as e:
            logger.error("[АВТОЛОТЫ] Не удалось удалить ID подкатегорий.")
            logger.debug("TRACEBACK", exc_info=True)
            bot.send_message(m.chat.id, f"❌ Не удалось удалить ID подкатегорий. Ошибка: {str(e)}")

    exfa.add_telegram_commands(UUID, [
        ("lots_find_id", "кэширует активные лоты в файл", True),
        ("set_subcategories", "устанавливает ID подкатегорий для получения лотов", True),
        ("lots_ids", "показывает все ID подкатегорий", True),
        ("delete_lots_id", "удаляет указанные ID подкатегорий", True),
    ])

    tg.msg_handler(lots_find_id, commands=["lots_find_id"])
    tg.msg_handler(set_subcategories, commands=["set_subcategories"])
    tg.msg_handler(show_lots_ids, commands=["lots_ids"])
    tg.msg_handler(delete_lots_ids, commands=["delete_lots_id"])

    settings_auto_path = "storage/plugins/settings_auto.json"
    if exists(settings_auto_path):
        with open(settings_auto_path, "r", encoding="utf-8") as f:
            settings_auto = json.loads(f.read())
            logger.info(f"[АВТОЛОТЫ] Настройки subcategory_ids загружены: {settings_auto.get('subcategory_ids', [])}")
    else:
        logger.info("[АВТОЛОТЫ] Файл settings_auto.json не найден. Используются значения по умолчанию.")

BIND_TO_PRE_INIT = [init_commands]
BIND_TO_DELETE = None