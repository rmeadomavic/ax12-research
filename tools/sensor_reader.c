/*
 * sensor_reader.c - Native Android sensor reader for RadioMaster AX12
 *
 * Reads accelerometer, gyroscope, and magnetometer data from the ICM-42607
 * via Android's NDK ASensorManager API and outputs JSON lines to stdout.
 *
 * NOTE: As of firmware V1.1 (2026.3.23), the MTK sensor HAL on the AX12 has
 * a broken initialization path -- the sysfs control attributes expected by
 * the HAL (/sys/class/sensor/m_acc_misc/, /dev/m_acc_misc, etc.) are not
 * created at boot. This means sensor batch/enable operations fail with
 * EPERM ("Operation not permitted"). A firmware fix from RadioMaster is
 * needed to create these sysfs nodes.
 *
 * When sensors are working, this binary provides real-time JSON output
 * suitable for piping to imu_tracker.py.
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

void accel_to_tilt(float ax, float ay, float az, float *pitch, float *roll) {
    *pitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * 180.0f / (float)M_PI;
    *roll  = atan2f(ay, az) * 180.0f / (float)M_PI;
}

typedef ASensorManager* (*getInstanceForPackage_t)(const char*);
typedef ASensorManager* (*getInstance_t)(void);

ASensorManager* get_sensor_manager(void) {
    void *lib = dlopen("libandroid.so", RTLD_NOW);
    if (!lib) {
        fprintf(stderr, "dlopen libandroid.so failed: %s\n", dlerror());
        return NULL;
    }
    getInstanceForPackage_t getForPkg =
        (getInstanceForPackage_t)dlsym(lib, "ASensorManager_getInstanceForPackage");
    if (getForPkg) {
        ASensorManager *mgr = getForPkg("com.termux");
        if (mgr) return mgr;
    }
    getInstance_t getInst = (getInstance_t)dlsym(lib, "ASensorManager_getInstance");
    if (getInst) return getInst();
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

    ASensorManager *mgr = get_sensor_manager();
    if (!mgr) {
        fprintf(stderr, "ERROR: Cannot get ASensorManager instance\n");
        return 1;
    }

    ASensorList sensor_list;
    int num_sensors = ASensorManager_getSensorList(mgr, &sensor_list);
    fprintf(stderr, "Available sensors: %d\n", num_sensors);
    for (int i = 0; i < num_sensors; i++) {
        fprintf(stderr, "  [%d] %s (type=%d)\n", i,
                ASensor_getName(sensor_list[i]),
                ASensor_getType(sensor_list[i]));
    }

    const ASensor *accel = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_ACCELEROMETER);
    const ASensor *gyro  = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_GYROSCOPE);
    const ASensor *mag   = ASensorManager_getDefaultSensor(mgr, ASENSOR_TYPE_MAGNETIC_FIELD);

    if (!accel) {
        fprintf(stderr, "ERROR: No accelerometer found\n");
        return 1;
    }

    ALooper *looper = ALooper_prepare(ALOOPER_PREPARE_ALLOW_NON_CALLBACKS);
    if (!looper) { fprintf(stderr, "ERROR: Cannot prepare ALooper\n"); return 1; }

    ASensorEventQueue *queue = ASensorManager_createEventQueue(mgr, looper, 1, NULL, NULL);
    if (!queue) { fprintf(stderr, "ERROR: Cannot create event queue\n"); return 1; }

    int rc = ASensorEventQueue_enableSensor(queue, accel);
    if (rc != 0) {
        fprintf(stderr, "ERROR: Cannot enable accelerometer (rc=%d)\n", rc);
        fprintf(stderr, "This likely means the MTK sensor HAL is not functioning.\n");
        fprintf(stderr, "Check: ls /dev/m_acc_misc /sys/class/sensor/m_acc_misc/\n");
        ASensorManager_destroyEventQueue(mgr, queue);
        return 2;
    }
    ASensorEventQueue_setEventRate(queue, accel, sample_period_us);

    if (gyro) {
        rc = ASensorEventQueue_enableSensor(queue, gyro);
        if (rc == 0) ASensorEventQueue_setEventRate(queue, gyro, sample_period_us);
        else fprintf(stderr, "WARNING: Cannot enable gyroscope\n");
    }
    if (mag) {
        rc = ASensorEventQueue_enableSensor(queue, mag);
        if (rc == 0) ASensorEventQueue_setEventRate(queue, mag, sample_period_us);
        else fprintf(stderr, "WARNING: Cannot enable magnetometer\n");
    }

    printf("{\"type\":\"header\",\"sensors\":{\"accel\":true,\"gyro\":%s,\"mag\":%s},\"rate_hz\":%d}\n",
           gyro ? "true" : "false", mag ? "true" : "false", rate_hz);
    fflush(stdout);

    struct timespec start_ts;
    clock_gettime(CLOCK_MONOTONIC, &start_ts);
    float last_ax=0, last_ay=0, last_az=0;
    float last_gx=0, last_gy=0, last_gz=0;
    float last_mx=0, last_my=0, last_mz=0;
    int sample_count = 0;

    while (running) {
        if (duration_sec > 0) {
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            double elapsed = (now.tv_sec - start_ts.tv_sec) + (now.tv_nsec - start_ts.tv_nsec)/1e9;
            if (elapsed >= duration_sec) break;
        }
        ALooper_pollOnce(100, NULL, NULL, NULL);
        ASensorEvent events[64];
        ssize_t n = ASensorEventQueue_getEvents(queue, events, 64);
        for (ssize_t i = 0; i < n; i++) {
            switch (events[i].type) {
                case ASENSOR_TYPE_ACCELEROMETER:
                    last_ax = events[i].acceleration.x;
                    last_ay = events[i].acceleration.y;
                    last_az = events[i].acceleration.z;
                    { float pitch, roll;
                      accel_to_tilt(last_ax, last_ay, last_az, &pitch, &roll);
                      float heading = 0;
                      if (mag && (last_mx||last_my||last_mz)) {
                          float cp=cosf(pitch*M_PI/180), sp=sinf(pitch*M_PI/180);
                          float cr=cosf(roll*M_PI/180), sr=sinf(roll*M_PI/180);
                          float mxc=last_mx*cp+last_mz*sp;
                          float myc=last_mx*sr*sp+last_my*cr-last_mz*sr*cp;
                          heading=atan2f(-myc,mxc)*180/M_PI; if(heading<0)heading+=360;
                      }
                      struct timespec now; clock_gettime(CLOCK_MONOTONIC,&now);
                      double el=(now.tv_sec-start_ts.tv_sec)+(now.tv_nsec-start_ts.tv_nsec)/1e9;
                      printf("{\"t\":%.3f,\"n\":%d,\"accel\":[%.4f,%.4f,%.4f],"
                             "\"gyro\":[%.4f,%.4f,%.4f],\"mag\":[%.2f,%.2f,%.2f],"
                             "\"pitch\":%.2f,\"roll\":%.2f,\"heading\":%.1f}\n",
                             el,sample_count,last_ax,last_ay,last_az,
                             last_gx,last_gy,last_gz,last_mx,last_my,last_mz,pitch,roll,heading);
                      fflush(stdout); sample_count++;
                    } break;
                case ASENSOR_TYPE_GYROSCOPE:
                    last_gx=events[i].gyro.x; last_gy=events[i].gyro.y; last_gz=events[i].gyro.z; break;
                case ASENSOR_TYPE_MAGNETIC_FIELD:
                    last_mx=events[i].magnetic.x; last_my=events[i].magnetic.y; last_mz=events[i].magnetic.z; break;
            }
        }
    }

    ASensorEventQueue_disableSensor(queue, accel);
    if (gyro) ASensorEventQueue_disableSensor(queue, gyro);
    if (mag) ASensorEventQueue_disableSensor(queue, mag);
    ASensorManager_destroyEventQueue(mgr, queue);
    fprintf(stderr, "---\nTotal samples: %d\n", sample_count);
    return 0;
}
