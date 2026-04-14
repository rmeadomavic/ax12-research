/*
 * sensor_reader.c - Direct I2C sensor reader for AX12 ICM-42607
 *
 * Reads accelerometer, gyroscope, and temperature data directly from
 * the ICM-42607 IMU via /dev/i2c-1 (address 0x10), bypassing Android
 * SensorManager. Also reads the magnetometer if found.
 *
 * The ICM-42607 on the AX12 is managed by the MTK SCP (sensor co-processor),
 * so we need to be careful not to conflict with the HAL. We read registers
 * directly and output JSON lines.
 *
 * Compile on AX12 (Termux):
 *   clang -O2 -o sensor_reader sensor_reader.c -lm
 *
 * Run:
 *   su 0 ./sensor_reader [duration_sec] [rate_hz]
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <time.h>
#include <math.h>
#include <signal.h>
#include <errno.h>
#include <stdint.h>

/* I2C ioctl definitions */
#define I2C_SLAVE       0x0703
#define I2C_SLAVE_FORCE 0x0706
#define I2C_RDWR        0x0707

struct i2c_msg {
    uint16_t addr;
    uint16_t flags;
#define I2C_M_RD  0x0001
    uint16_t len;
    uint8_t *buf;
};

struct i2c_rdwr_ioctl_data {
    struct i2c_msg *msgs;
    uint32_t nmsgs;
};

/* ICM-42607 register map (Bank 0) */
#define ICM_WHO_AM_I       0x75  /* Should return 0x60 for ICM-42607 */
#define ICM_PWR_MGMT0      0x1F
#define ICM_GYRO_CONFIG0    0x20
#define ICM_ACCEL_CONFIG0   0x21
#define ICM_TEMP_DATA1      0x09
#define ICM_TEMP_DATA0      0x0A
#define ICM_ACCEL_DATA_X1   0x0B
#define ICM_ACCEL_DATA_X0   0x0C
#define ICM_ACCEL_DATA_Y1   0x0D
#define ICM_ACCEL_DATA_Y0   0x0E
#define ICM_ACCEL_DATA_Z1   0x0F
#define ICM_ACCEL_DATA_Z0   0x10
#define ICM_GYRO_DATA_X1    0x11
#define ICM_GYRO_DATA_X0    0x12
#define ICM_GYRO_DATA_Y1    0x13
#define ICM_GYRO_DATA_Y0    0x14
#define ICM_GYRO_DATA_Z1    0x15
#define ICM_GYRO_DATA_Z0    0x16
#define ICM_INT_STATUS      0x3A

/* ICM-42607 constants */
#define ICM_ACCEL_MODE_LN   0x03  /* Accel low-noise mode */
#define ICM_GYRO_MODE_LN    0x0C  /* Gyro low-noise mode */

/* Sensitivity scale factors (default FS settings) */
/* Accel: +/-16g = 2048 LSB/g */
/* Gyro: +/-2000 dps = 16.4 LSB/dps */
#define ACCEL_SENSITIVITY_16G  2048.0f
#define GYRO_SENSITIVITY_2000  16.4f
/* Accel: +/-4g (more common default) = 8192 LSB/g */
#define ACCEL_SENSITIVITY_4G   8192.0f
/* Gyro: +/-250 dps = 131.0 LSB/dps */
#define GYRO_SENSITIVITY_250   131.0f

static volatile int running = 1;
static int i2c_fd = -1;

void sighandler(int sig) {
    (void)sig;
    running = 0;
}

/* I2C read using ioctl I2C_RDWR (works even when device is bound to driver) */
int i2c_read_reg(int fd, uint8_t addr, uint8_t reg, uint8_t *buf, int len) {
    struct i2c_msg msgs[2];
    struct i2c_rdwr_ioctl_data data;

    msgs[0].addr = addr;
    msgs[0].flags = 0;  /* write */
    msgs[0].len = 1;
    msgs[0].buf = &reg;

    msgs[1].addr = addr;
    msgs[1].flags = I2C_M_RD;
    msgs[1].len = len;
    msgs[1].buf = buf;

    data.msgs = msgs;
    data.nmsgs = 2;

    if (ioctl(fd, I2C_RDWR, &data) < 0) {
        return -1;
    }
    return 0;
}

int i2c_write_reg(int fd, uint8_t addr, uint8_t reg, uint8_t val) {
    uint8_t buf[2] = {reg, val};
    struct i2c_msg msg;
    struct i2c_rdwr_ioctl_data data;

    msg.addr = addr;
    msg.flags = 0;
    msg.len = 2;
    msg.buf = buf;

    data.msgs = &msg;
    data.nmsgs = 1;

    if (ioctl(fd, I2C_RDWR, &data) < 0) {
        return -1;
    }
    return 0;
}

void accel_to_tilt(float ax, float ay, float az, float *pitch, float *roll) {
    *pitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * 180.0f / (float)M_PI;
    *roll  = atan2f(ay, az) * 180.0f / (float)M_PI;
}

int main(int argc, char *argv[]) {
    int duration_sec = 10;
    int rate_hz = 25;
    const char *i2c_dev = "/dev/i2c-1";
    uint8_t icm_addr = 0x10;  /* ICM-42607 address on AX12 (gsensor_a) */

    if (argc > 1) duration_sec = atoi(argv[1]);
    if (argc > 2) rate_hz = atoi(argv[2]);
    if (argc > 3) i2c_dev = argv[3];
    if (argc > 4) icm_addr = (uint8_t)strtol(argv[4], NULL, 0);
    if (rate_hz < 1) rate_hz = 25;

    int sleep_us = 1000000 / rate_hz;

    signal(SIGINT, sighandler);
    signal(SIGTERM, sighandler);

    /* Open I2C bus */
    i2c_fd = open(i2c_dev, O_RDWR);
    if (i2c_fd < 0) {
        fprintf(stderr, "ERROR: Cannot open %s: %s\n", i2c_dev, strerror(errno));
        return 1;
    }

    fprintf(stderr, "Opened %s\n", i2c_dev);

    /* Read WHO_AM_I to verify chip */
    uint8_t who_am_i = 0;
    if (i2c_read_reg(i2c_fd, icm_addr, ICM_WHO_AM_I, &who_am_i, 1) < 0) {
        fprintf(stderr, "ERROR: Cannot read WHO_AM_I from 0x%02x: %s\n", icm_addr, strerror(errno));
        fprintf(stderr, "Trying alternate address 0x68...\n");
        icm_addr = 0x68;
        if (i2c_read_reg(i2c_fd, icm_addr, ICM_WHO_AM_I, &who_am_i, 1) < 0) {
            fprintf(stderr, "ERROR: Also failed at 0x68: %s\n", strerror(errno));
            close(i2c_fd);
            return 1;
        }
    }
    fprintf(stderr, "WHO_AM_I: 0x%02x (addr=0x%02x)\n", who_am_i, icm_addr);

    /* Check if ICM-42607 (0x60) or compatible */
    if (who_am_i != 0x60 && who_am_i != 0x67 && who_am_i != 0x6B) {
        fprintf(stderr, "WARNING: Unexpected WHO_AM_I 0x%02x (expected 0x60 for ICM-42607)\n", who_am_i);
    }

    /* Read current power management state */
    uint8_t pwr;
    i2c_read_reg(i2c_fd, icm_addr, ICM_PWR_MGMT0, &pwr, 1);
    fprintf(stderr, "PWR_MGMT0 current: 0x%02x\n", pwr);

    /* Check if sensors are already enabled by the SCP/HAL */
    int accel_was_on = (pwr & 0x03) != 0;
    int gyro_was_on = (pwr & 0x0C) != 0;
    fprintf(stderr, "Accel was %s, Gyro was %s\n",
            accel_was_on ? "ON" : "OFF",
            gyro_was_on ? "ON" : "OFF");

    /* Enable both accel and gyro in low-noise mode if not already on */
    if (!accel_was_on || !gyro_was_on) {
        uint8_t new_pwr = pwr | ICM_ACCEL_MODE_LN | ICM_GYRO_MODE_LN;
        if (i2c_write_reg(i2c_fd, icm_addr, ICM_PWR_MGMT0, new_pwr) < 0) {
            fprintf(stderr, "WARNING: Cannot write PWR_MGMT0 (SCP may control it): %s\n", strerror(errno));
        } else {
            fprintf(stderr, "PWR_MGMT0 set to 0x%02x\n", new_pwr);
            usleep(50000); /* Wait 50ms for sensors to start */
        }
    }

    /* Read config to determine sensitivity */
    uint8_t accel_config, gyro_config;
    i2c_read_reg(i2c_fd, icm_addr, ICM_ACCEL_CONFIG0, &accel_config, 1);
    i2c_read_reg(i2c_fd, icm_addr, ICM_GYRO_CONFIG0, &gyro_config, 1);
    fprintf(stderr, "ACCEL_CONFIG0: 0x%02x, GYRO_CONFIG0: 0x%02x\n", accel_config, gyro_config);

    /* Determine scale factors from FS_SEL bits */
    float accel_scale, gyro_scale;
    int accel_fs = (accel_config >> 5) & 0x07;
    int gyro_fs = (gyro_config >> 5) & 0x07;

    switch (accel_fs) {
        case 0: accel_scale = 2048.0f; break;   /* +/-16g */
        case 1: accel_scale = 4096.0f; break;   /* +/-8g */
        case 2: accel_scale = 8192.0f; break;   /* +/-4g */
        case 3: accel_scale = 16384.0f; break;  /* +/-2g */
        default: accel_scale = 8192.0f;
    }
    switch (gyro_fs) {
        case 0: gyro_scale = 16.4f; break;      /* +/-2000 dps */
        case 1: gyro_scale = 32.8f; break;      /* +/-1000 dps */
        case 2: gyro_scale = 65.5f; break;      /* +/-500 dps */
        case 3: gyro_scale = 131.0f; break;     /* +/-250 dps */
        default: gyro_scale = 131.0f;
    }
    fprintf(stderr, "Accel FS_SEL=%d (scale=%.1f LSB/g), Gyro FS_SEL=%d (scale=%.1f LSB/dps)\n",
            accel_fs, accel_scale, gyro_fs, gyro_scale);

    /* Output JSON header */
    printf("{\"type\":\"header\",\"chip\":\"ICM-42607\",\"who_am_i\":\"0x%02x\","
           "\"i2c\":\"%s@0x%02x\",\"rate_hz\":%d,"
           "\"accel_fs\":%d,\"gyro_fs\":%d}\n",
           who_am_i, i2c_dev, icm_addr, rate_hz, accel_fs, gyro_fs);
    fflush(stdout);

    fprintf(stderr, "---\nReading sensors at %dHz...\n", rate_hz);
    fflush(stderr);

    struct timespec start_ts;
    clock_gettime(CLOCK_MONOTONIC, &start_ts);

    int sample_count = 0;
    int err_count = 0;

    while (running) {
        /* Check duration */
        if (duration_sec > 0) {
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            double elapsed = (now.tv_sec - start_ts.tv_sec)
                           + (now.tv_nsec - start_ts.tv_nsec) / 1e9;
            if (elapsed >= duration_sec) break;
        }

        /* Read all sensor data registers in one burst (0x09 to 0x16 = 14 bytes) */
        uint8_t raw[14];
        if (i2c_read_reg(i2c_fd, icm_addr, ICM_TEMP_DATA1, raw, 14) < 0) {
            err_count++;
            if (err_count > 10) {
                fprintf(stderr, "Too many read errors, aborting\n");
                break;
            }
            usleep(sleep_us);
            continue;
        }

        /* Parse raw data (big-endian 16-bit signed) */
        int16_t temp_raw = (int16_t)((raw[0] << 8) | raw[1]);
        int16_t ax_raw = (int16_t)((raw[2] << 8) | raw[3]);
        int16_t ay_raw = (int16_t)((raw[4] << 8) | raw[5]);
        int16_t az_raw = (int16_t)((raw[6] << 8) | raw[7]);
        int16_t gx_raw = (int16_t)((raw[8] << 8) | raw[9]);
        int16_t gy_raw = (int16_t)((raw[10] << 8) | raw[11]);
        int16_t gz_raw = (int16_t)((raw[12] << 8) | raw[13]);

        /* Convert to physical units */
        float temp_c = (float)temp_raw / 128.0f + 25.0f;
        float ax = (float)ax_raw / accel_scale * 9.80665f;  /* m/s^2 */
        float ay = (float)ay_raw / accel_scale * 9.80665f;
        float az = (float)az_raw / accel_scale * 9.80665f;
        float gx = (float)gx_raw / gyro_scale * (M_PI / 180.0f);  /* rad/s */
        float gy = (float)gy_raw / gyro_scale * (M_PI / 180.0f);
        float gz = (float)gz_raw / gyro_scale * (M_PI / 180.0f);

        /* Compute tilt angles */
        float pitch, roll;
        accel_to_tilt(ax, ay, az, &pitch, &roll);

        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (now.tv_sec - start_ts.tv_sec)
                       + (now.tv_nsec - start_ts.tv_nsec) / 1e9;

        printf("{\"t\":%.3f,\"n\":%d,"
               "\"accel\":[%.4f,%.4f,%.4f],"
               "\"gyro\":[%.4f,%.4f,%.4f],"
               "\"mag\":[0.00,0.00,0.00],"
               "\"temp\":%.1f,"
               "\"pitch\":%.2f,\"roll\":%.2f,\"heading\":0.0}\n",
               elapsed, sample_count,
               ax, ay, az,
               gx, gy, gz,
               temp_c,
               pitch, roll);
        fflush(stdout);
        sample_count++;

        usleep(sleep_us);
    }

    /* Restore original power state if we changed it */
    if (!accel_was_on || !gyro_was_on) {
        i2c_write_reg(i2c_fd, icm_addr, ICM_PWR_MGMT0, pwr);
        fprintf(stderr, "Restored PWR_MGMT0 to 0x%02x\n", pwr);
    }

    close(i2c_fd);
    fprintf(stderr, "---\nTotal samples: %d (errors: %d)\n", sample_count, err_count);
    return 0;
}
