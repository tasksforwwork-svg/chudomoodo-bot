def main():
    init_db()
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=daily_scheduler, daemon=True)
    scheduler_thread.start()
    
    offset = None
    while True:
        try:
            updates = get_updates(offset, POLL_TIMEOUT)
            for update in updates:
                process_incoming_message(update)
                # Убедимся, что offset увеличивается правильно
                offset = update.get("update_id", 0) + 1
            time.sleep(POLL_SLEEP)
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(POLL_SLEEP)
