def main():
    init_db()
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=daily_scheduler, daemon=True)
    scheduler_thread.start()
    
    offset = None
    processed_updates = set()  # Для отслеживания уже обработанных update_id
    
    while True:
        try:
            updates = get_updates(offset, POLL_TIMEOUT)
            print(f"DEBUG: Got {len(updates)} updates")
            
            for update in updates:
                update_id = update.get("update_id")
                
                # Проверяем, не обрабатывали ли мы уже этот update
                if update_id in processed_updates:
                    print(f"DEBUG: Skipping already processed update {update_id}")
                    offset = update_id + 1
                    continue
                    
                print(f"DEBUG: Processing update {update_id}")
                process_incoming_message(update)
                processed_updates.add(update_id)
                offset = update_id + 1
                
                # Очищаем старые update_id чтобы не накапливать слишком много
                if len(processed_updates) > 1000:
                    # Оставляем только последние 500
                    processed_updates = set(list(processed_updates)[-500:])
                    
            time.sleep(POLL_SLEEP)
            
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(POLL_SLEEP)
