package com.safety.common.util;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class MemoryStore {

    private final Map<String, Entry> store = new ConcurrentHashMap<>();

    public void set(String key, String value, long ttlSeconds) {
        store.put(key, new Entry(value, System.currentTimeMillis() + ttlSeconds * 1000));
    }

    public String get(String key) {
        Entry entry = store.get(key);
        if (entry == null) return null;
        if (System.currentTimeMillis() > entry.expireAt) {
            store.remove(key);
            return null;
        }
        return entry.value;
    }

    public void delete(String key) {
        store.remove(key);
    }

    private record Entry(String value, long expireAt) {}
}
