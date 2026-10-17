/*
 * ESP32 Classroom BLE Beacon Transmitter with Anti-Rogue Cryptographic Auth
 * 
 * Project: IERT Smart Attendance System
 * Target Hardware: ESP32 Dev Module / NodeMCU-32S / ESP-WROOM-32
 * 
 * This firmware turns an ESP32 into a secure BLE Classroom Beacon.
 * Features:
 * 1. Standard Apple iBeacon payload (UUID, Major, Minor, RSSI).
 * 2. Anti-Rogue ESP32 Protection: Computes rolling HMAC-SHA256 Minor tokens
 *    synchronized via NTP to prevent students bringing personal unauthorized ESP32s.
 * 3. Graceful Fallback: Operates in standard static Minor mode if offline.
 * 
 * CONFIGURATION:
 * 1. Private settings are loaded from "beacon_config.h" (ignored by git).
 * 2. If not present, fallback settings are loaded from "beacon_config.h.example".
 */

#include <Arduino.h>
#include <WiFi.h>
#include <time.h>
#include "BLEDevice.h"
#include "BLEUtils.h"
#include "BLEServer.h"
#include "BLEBeacon.h"
#include "esp_sleep.h"
#include "mbedtls/md.h"

// ----------------------------------------------------------------------------
// Configuration Loader
// ----------------------------------------------------------------------------
#if __has_include("beacon_config.h")
    #include "beacon_config.h"
#elif __has_include("beacon_config.h.example")
    #include "beacon_config.h.example"
#else
    #define BEACON_UUID           "00000000-0000-0000-0000-000000000000"
    #define BEACON_UUID_REV       "00000000-0000-0000-0000-000000000000"
    #define BEACON_NAME           "SAS_Classroom_Beacon"
    #define CLASSROOM_ID          1
    #define LED_PIN               2
    #define ENABLE_ROLLING_AUTH   false
    #define BEACON_SECRET_KEY     "iert_beacon_secret_salt_2026_xyz"
    #define WIFI_SSID             "IERT_CAMPUS_WIFI"
    #define WIFI_PASS             "campus_secure_pass"
#endif

#ifndef CLASSROOM_ID
#define CLASSROOM_ID 1
#endif

#ifndef ENABLE_ROLLING_AUTH
#define ENABLE_ROLLING_AUTH false
#endif

#ifndef BEACON_SECRET_KEY
#define BEACON_SECRET_KEY "iert_beacon_secret_salt_2026_xyz"
#endif

BLEAdvertising *pAdvertising;
uint16_t currentMinor = 101;
uint32_t lastTokenUpdate = 0;

uint16_t computeRollingMinor(uint16_t classroomId, uint32_t epochSeconds, const char* secretKey) {
    uint32_t minuteSlot = epochSeconds / 60;
    char msg[64];
    snprintf(msg, sizeof(msg), "IERT_BEACON_%u_%u", classroomId, minuteSlot);

    byte hmacResult[32];
    mbedtls_md_context_t ctx;
    mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
    mbedtls_md_hmac_starts(&ctx, (const unsigned char*)secretKey, strlen(secretKey));
    mbedtls_md_hmac_update(&ctx, (const unsigned char*)msg, strlen(msg));
    mbedtls_md_hmac_finish(&ctx, hmacResult);
    mbedtls_md_free(&ctx);

    uint16_t minor = (hmacResult[0] << 8) | hmacResult[1];
    return (minor == 0) ? 1 : minor;
}

void setBeacon(uint16_t minorCode) {
    BLEBeacon oBeacon = BLEBeacon();
    oBeacon.setManufacturerId(0x4C00); // Apple iBeacon format (0x004C)
    
    // Set UUID (using reversed byte string so broadcasted packet matches BEACON_UUID exactly)
    oBeacon.setProximityUUID(BLEUUID(BEACON_UUID_REV));
    oBeacon.setMajor(CLASSROOM_ID);      // Room / Classroom number (e.g. Room 1)
    oBeacon.setMinor(minorCode);         // Section or Cryptographic Rolling Minor
    oBeacon.setSignalPower(-59);         // Measured RSSI power at 1 meter

    BLEAdvertisementData oAdvertisementData;
    BLEAdvertisementData oScanResponseData;

    oAdvertisementData.setFlags(0x04); // BR_EDR_NOT_SUPPORTED 0x04 (BLE Only)
    oAdvertisementData.setManufacturerData(oBeacon.getData());
    oScanResponseData.setName(BEACON_NAME);

    pAdvertising->setAdvertisementData(oAdvertisementData);
    pAdvertising->setScanResponseData(oScanResponseData);
    pAdvertising->setScanResponse(true);
}

void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);

    Serial.println("\n==========================================");
    Serial.println("  IERT Smart Attendance - Classroom Beacon");
    Serial.println("==========================================");
    Serial.printf("Broadcasting UUID : %s\n", BEACON_UUID);
    Serial.printf("Beacon Name       : %s\n", BEACON_NAME);
    Serial.printf("Classroom / Room  : %d\n", CLASSROOM_ID);

#if ENABLE_ROLLING_AUTH
    Serial.println("Security Mode     : Anti-Rogue ESP32 (Rolling HMAC-SHA256)");
    Serial.printf("Connecting WiFi   : %s\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 15) {
        delay(500);
        Serial.print(".");
        retries++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("[NTP] Syncing institutional clock via pool.ntp.org...");
        configTime(19800, 0, "pool.ntp.org", "time.google.com"); // UTC+5:30 IST
        time_t now = 0;
        int ntpTries = 0;
        while (time(&now) < 100000 && ntpTries < 20) {
            delay(300);
            ntpTries++;
        }
        if (now > 100000) {
            currentMinor = computeRollingMinor(CLASSROOM_ID, now, BEACON_SECRET_KEY);
            Serial.printf("[Security] Rolling token initialized. Active Minor: %u\n", currentMinor);
        }
    } else {
        Serial.println("[WiFi] Connection timed out. Operating in offline static mode.");
    }
#else
    Serial.println("Security Mode     : Static Classroom Beacon");
#endif

    Serial.printf("Initial Minor     : %u\n", currentMinor);
    Serial.println("Status            : Active & Transmitting");
    Serial.println("==========================================\n");

    // Initialize BLE Device
    BLEDevice::init(BEACON_NAME);
    pAdvertising = BLEDevice::getAdvertising();

    setBeacon(currentMinor);

    // Start advertising
    pAdvertising->start();
    Serial.println("[BLE] Beacon is now LIVE. Students' phones will detect it automatically.\n");
}

void loop() {
#if ENABLE_ROLLING_AUTH
    // Rotate token every 60 seconds
    time_t now;
    time(&now);
    if (now > 100000 && (millis() - lastTokenUpdate >= 60000)) {
        uint16_t nextMinor = computeRollingMinor(CLASSROOM_ID, now, BEACON_SECRET_KEY);
        if (nextMinor != currentMinor) {
            currentMinor = nextMinor;
            pAdvertising->stop();
            setBeacon(currentMinor);
            pAdvertising->start();
            Serial.printf("[Security] Rotated rolling beacon Minor to: %u (Time: %lu)\n", currentMinor, (unsigned long)now);
        }
        lastTokenUpdate = millis();
    }
#endif

    // Heartbeat: blink onboard LED every 3 seconds to indicate healthy beacon transmission
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(2900);
}