/*
 * sensor_reader.c - Native Android sensor reader for RadioMaster AX12
 *
 * Reads IMU data (accelerometer, gyroscope, magnetometer)
 * via Android NDK ASensorManager API and outputs JSON lines to stdout.
 *
 * Uses dlsym to call ASensorManager_getInstanceForPackage at runtime
 * (bypasses compile-time API level restrictions).
 *
 * Compile on AX12 (Termux):
 *   clang -O2 -o sensor_reader sensor_reader.c -landroid -llog -lm -ldl
 *
 * Usage:
 *   ./sensor_reader [duration_sec] [rate_hz]
 *   ./sensor_reader 10 50    # 10 seconds at 50Hz
 *   ./sensor_reader 0 25     # run forever at 25Hz
 */

#include <android/sensor.h>
#include <android/looper.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <signal.h>
#include <unistd.h>
#include <dlfcn.h>

static volatile int running = 1;

void sighandler(int sig) {
    (void)sig;
    running = 0;
}

/* Convert accelerometer data to pitch/roll (tilt angles) */
void accel_to_tilt(float ax, float ay, float az, float *pitch, float *roll) {
    *pitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * 180.0f / (float)M_PI;
    *roll  = atan2f(ay, az) * 180.0f / (float)M_PI;
}

/* Function pointer types for dynamically loaded functions */
typedef ASensorManager* (*getInstanceForPackage_t)(const char*);
typedef ASensorManager* (*getInstance_t)(void);

ASensorManager* get_sensor_manager(void) {
    /* Try to load libandroid.so and find getInstanceForPackage */
    void *lib = dlopen("libandroid.so", RTLD_NOW);
    if (!lib) {
        fprintf(stderr, "dlopen libandroid.so failed: %s\n", dlerror());
        return NULL;
    }

    /* Try getInstanceForPackage first (Android 8.0+) */
    getInstanceForPackage_t getForPkg =
        (getInstanceForPackage_t)dlsym(lib, "ASensorManager_getInstanceForPackage");
    if (getForPkg) {
        fprintf(stderr, "Using ASensorManager_getInstanceForPackage\n");
        ASensorManager *mgr = getForPkg("com.termux");
        if (mgr) return mgr;
        fprintf(stderr, "getInstanceForPackage returned NULL, trying system package\n");
        mgr = getForPkg("android");
        if (mgr) return mgr;
    }

    /* Fall back to getInstance (deprecated but works) */
    getInstance_t getInst =
        (getInstance_t)dlsym(lib, "ASensorManager_getInstance");
    if (getInst) {
        fprintf(stderr, "Using ASensorManager_getInstance (deprecated)\n");
        return getInst();
    }

    fprintf(stderr, "No sensor manager function found\n");
    return NULL;
}

int main(int argc, char *argv[]) {
    int duration_sec = 10;
    int rate_hz = 25;

    if (argc > 1) duration_sec = atoi(argv[1]);
    if (argc > 2) rate_hz = atoi(argv[2]);
    if (rate_hz < 1) rate_hz = 25;

    int sample_period_us = 1000000 / rate_hz;

    signal(SIGINT, sighandler);
    signal(SIGTERM, sighandler);

    /* Get sensor manager via dlsym */
    ASensorManager *mgr = get_sensor_manager();
    if (!mgr) {
        fprintf(stderr, "ERROR: Cannot get ASensorManager instance\n");
        return 1;
    }

    /* List all available sensors */
    ASensorList sensor_list;
    int num_sensors = ASensorManager_getSensorList(mgr, &sensor_list);
    fprintf(stderr, "Available sensors: %d\n", num_sensors);
    for (int i = 0; i < num_sensors; i++) {
        fprintf(stderr, "  [%d] %s (type=%d, minDelay=%d us)\n", i,
                ASensor_getName(sensor_list[i]),
                ASensor_getType(sensor_list[i]),
                ASensor_getMinDelay(sensor_list[i]));
    }

    /* Get sensors */
    const ASensor *accel = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_ACCELEROMETER);
    const ASensor *gyro  = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_GYROSCOPE);
    const ASensor *mag   = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_MAGNETIC_FIELD);

    if (!accel) {
        fprintf(stderr, "ERROR: No accelerometer found\n");
        return 1;
    }

    /* Create looper for this thread */
    ALooper *looper = ALooper_prepare(ALOOPER_PREPARE_ALLOW_NON_CALLBACKS);
    if (!looper) {
        fprintf(stderr, "ERROR: Cannot prepare ALooper\n");
        return 1;
    }

    /* Create event queue */
    ASensorEventQueue *queue = ASensorManager_createEventQueue(
        mgr, looper, 1, NULL, NULL);
    if (!queue) {
        fprintf(stderr, "ERROR: Cannot create sensor event queue\n");
        return 1;
    }
    fprintf(stderr, "Event queue created\n");

    /* Enable sensors */
    int rc;
    rc = ASensorEventQueue_enableSensor(queue, accel);
    fprintf(stderr, "Enable accel: rc=%d\n", rc);
    if (rc == 0) {
        rc = ASensorEventQueue_setEventRate(queue, accel, sample_period_us);
        fprintf(stderr, "Set accel rate (%d us): rc=%d\n", sample_period_us, rc);
    }

    if (gyro) {
        rc = ASensorEventQueue_enableSensor(queue, gyro);
        fprintf(stderr, "Enable gyro: rc=%d\n", rc);
        if (rc == 0) {
            rc = ASensorEventQueue_setEventRate(queue, gyro, sample_period_us);
            fprintf(stderr, "Set gyro rate: rc=%d\n", rc);
        }
    }

    if (mag) {
        rc = ASensorEventQueue_enableSensor(queue, mag);
        fprintf(stderr, "Enable mag: rc=%d\n", rc);
        if (rc == 0) {
            rc = ASensorEventQueue_setEventRate(queue, mag, sample_period_us);
            fprintf(stderr, "Set mag rate: rc=%d\n", rc);
        }
    }

    fprintf(stderr, "---\nPolling...\n");
    fflush(stderr);

    /* Output JSON header */
    printf("{\"type\":\"header\",\"sensors\":{\"accel\":%s,\"gyro\":%s,\"mag\":%s},\"rate_hz\":%d}\n",
           accel ? "true" : "false",
           gyro ? "true" : "false",
           mag ? "true" : "false",
           rate_hz);
    fflush(stdout);

    struct timespec start_ts;
    clock_gettime(CLOCK_MONOTONIC, &start_ts);

    float last_ax = 0, last_ay = 0, last_az = 0;
    float last_gx = 0, last_gy = 0, last_gz = 0;
    float last_mx = 0, last_my = 0, last_mz = 0;
    int sample_count = 0;

    while (running) {
        /* Check duration */
        if (duration_sec > 0) {
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            double elapsed = (now.tv_sec - start_ts.tv_sec)
                           + (now.tv_nsec - start_ts.tv_nsec) / 1e9;
            if (elapsed >= duration_sec) break;
        }

        /* Poll looper */
        ALooper_pollOnce(100, NULL, NULL, NULL);

        /* Read events */
        ASensorEvent events[64];
        ssize_t n = ASensorEventQueue_getEvents(queue, events, 64);

        for (ssize_t i = 0; i < n; i++) {
            switch (events[i].type) {
                case ASENSOR_TYPE_ACCELEROMETER:
                    last_ax = events[i].acceleration.x;
                    last_ay = events[i].acceleration.y;
                    last_az = events[i].acceleration.z;
                    {
                        float pitch, roll;
                        accel_to_tilt(last_ax, last_ay, last_az, &pitch, &roll);

                        float heading = 0;
                        if (mag && (last_mx != 0 || last_my != 0 || last_mz != 0)) {
                            float cos_p = cosf(pitch * (float)M_PI / 180.0f);
                            float sin_p = sinf(pitch * (float)M_PI / 180.0f);
                            float cos_r = cosf(roll * (float)M_PI / 180.0f);
                            float sin_r = sinf(roll * (float)M_PI / 180.0f);
                            float mx_c = last_mx * cos_p + last_mz * sin_p;
                            float my_c = last_mx * sin_r * sin_p
                                        + last_my * cos_r
                                        - last_mz * sin_r * cos_p;
                            heading = atan2f(-my_c, mx_c) * 180.0f / (float)M_PI;
                            if (heading < 0) heading += 360.0f;
                        }

                        struct timespec now;
                        clock_gettime(CLOCK_MONOTONIC, &now);
                        double elapsed = (now.tv_sec - start_ts.tv_sec)
                                       + (now.tv_nsec - start_ts.tv_nsec) / 1e9;

                        printf("{\"t\":%.3f,\"n\":%d,"
                               "\"accel\":[%.4f,%.4f,%.4f],"
                               "\"gyro\":[%.4f,%.4f,%.4f],"
                               "\"mag\":[%.2f,%.2f,%.2f],"
                               "\"pitch\":%.2f,\"roll\":%.2f,\"heading\":%.1f}\n",
                               elapsed, sample_count,
                               last_ax, last_ay, last_az,
                               last_gx, last_gy, last_gz,
                               last_mx, last_my, last_mz,
                               pitch, roll, heading);
                        fflush(stdout);
                        sample_count++;
                    }
                    break;
                case ASENSOR_TYPE_GYROSCOPE:
                    last_gx = events[i].gyro.x;
                    last_gy = events[i].gyro.y;
                    last_gz = events[i].gyro.z;
                    break;
                case ASENSOR_TYPE_MAGNETIC_FIELD:
                    last_mx = events[i].magnetic.x;
                    last_my = events[i].magnetic.y;
                    last_mz = events[i].magnetic.z;
                    break;
            }
        }
    }

    /* Cleanup */
    ASensorEventQueue_disableSensor(queue, accel);
    if (gyro) ASensorEventQueue_disableSensor(queue, gyro);
    if (mag) ASensorEventQueue_disableSensor(queue, mag);
    ASensorManager_destroyEventQueue(mgr, queue);

    fprintf(stderr, "---\nTotal samples: %d\n", sample_count);
    return 0;
}
