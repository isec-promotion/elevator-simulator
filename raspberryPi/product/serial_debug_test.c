// serial_debug_test.c
// シリアル通信デバッグテスト（POSIX termios版）
// ビルド例: gcc serial_debug_test.c -o serial_debug_test

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include <time.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/stat.h>

static volatile int running = 1;

// シグナルハンドラー (Ctrl+C でループを抜ける)
void handle_sigint(int sig) {
    (void)sig;
    running = 0;
}

// シリアルポートを開いて termios 設定を行う
//   portname: "/dev/ttyUSB0" など
//   nonblock: テストモードなら 1（ノンブロッキング）、モニタリングなら 0
//   戻り値: ファイルディスクリプタ (>=0) or エラーで -1
int open_serial(const char *portname, int nonblock) {
    int flags = O_RDWR | O_NOCTTY | (nonblock ? O_NONBLOCK : 0);
    int fd = open(portname, flags);
    if (fd < 0) return -1;

    // モニタリング時は VTIME/VMIN でタイムアウト制御するため
    if (!nonblock) {
        // ブロッキングモードに戻す
        fcntl(fd, F_SETFL, 0);

        struct termios tio;
        if (tcgetattr(fd, &tio) < 0) {
            close(fd);
            return -1;
        }
        // ボーレート設定
        cfsetispeed(&tio, B9600);
        cfsetospeed(&tio, B9600);
        // 8bit, Even parity, 1 stop bit
        tio.c_cflag &= ~CSIZE;
        tio.c_cflag |= CS8;
        tio.c_cflag |= PARENB;   // parity enable
        tio.c_cflag &= ~PARODD;  // even
        tio.c_cflag &= ~CSTOPB;  // 1 stop bit
        // raw モード
        tio.c_lflag = 0;
        tio.c_iflag = 0;
        tio.c_oflag = 0;
        // フレーム長(16)を指定。最大0.5秒待機。
        tio.c_cc[VMIN]  = 16;
        tio.c_cc[VTIME] = 5;
        if (tcsetattr(fd, TCSANOW, &tio) < 0) {
            close(fd);
            return -1;
        }
    }

    return fd;
}

// モニタリング処理
void monitor_serial(const char *port) {
    int fd = open_serial(port, 0);
    if (fd < 0) {
        fprintf(stderr, "❌ %s を開けません: %s\n", port, strerror(errno));
        return;
    }

    printf("📡 シリアルモニタリング開始: %s\n", port);
    printf("    設定: 9600bps, 8bit, Even parity, 1 stop bit\n");
    printf("    Ctrl+C で終了\n\n");

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    time_t last_activity = time(NULL);

    unsigned char buf[256];
    while (running) {
        int n = read(fd, buf, sizeof(buf));
        if (n < 0) {
            // 読み取りエラーなら少し待って再試行
            usleep(100000);
            continue;
        }
        if (n > 0) {
            // 受信あり
            char ts[16];
            time_t now = time(NULL);
            struct tm lt;
            localtime_r(&now, &lt);
            strftime(ts, sizeof(ts), "%H:%M:%S", &lt);

            // HEX 表示
            char hexstr[256*2+1] = {0};
            for (int i = 0; i < n; i++) {
                sprintf(hexstr + i*2, "%02X", buf[i]);
            }
            // ASCII 表示
            char ascstr[256+1] = {0};
            for (int i = 0; i < n; i++) {
                unsigned char b = buf[i];
                ascstr[i] = (b >= 32 && b <= 126) ? b : '.';
            }

            printf("[%s] 受信 (%dバイト)\n", ts, n);
            printf("  HEX  : %s\n", hexstr);
            printf("  ASCII: %s\n\n", ascstr);

            last_activity = now;
        } else {
            // タイムアウト (VTIME) で n == 0
            time_t now = time(NULL);
            if (now - last_activity > 10) {
                char ts[16];
                struct tm lt;
                localtime_r(&now, &lt);
                strftime(ts, sizeof(ts), "%H:%M:%S", &lt);
                printf("[%s] 待機中... (データなし)\n", ts);
                last_activity = now;
            }
        }
        // read 自体が最大 0.1s ブロックするので追加 Sleep は不要
    }

    printf("\n🛑 モニタリング終了\n");
    close(fd);
}

// ポート検索テスト
void test_serial_ports(void) {
    const char* ports[] = {
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyAMA0",
        "/dev/serial0",
        "/dev/ttyS0",
    };
    size_t cnt = sizeof(ports)/sizeof(ports[0]);

    printf("🔍 利用可能なシリアルポートを検索中...\n");
    for (size_t i = 0; i < cnt; i++) {
        int fd = open_serial(ports[i], 1);
        if (fd >= 0) {
            printf("✅ %s: 接続成功\n", ports[i]);
            close(fd);
        } else {
            printf("❌ %s: %s\n", ports[i], strerror(errno));
        }
    }
}

// エントリポイント
int main(int argc, char *argv[]) {
    if (argc > 1) {
        if (strcmp(argv[1], "test") == 0) {
            test_serial_ports();
            return 0;
        } else {
            monitor_serial(argv[1]);
            return 0;
        }
    }

    // 引数なし時
    printf("使用方法:\n");
    printf("  %s test          # ポート検索\n", argv[0]);
    printf("  %s /dev/ttyUSB0  # モニタリング\n\n", argv[0]);
    test_serial_ports();
    printf("\n");
    monitor_serial("/dev/ttyUSB0");
    return 0;
}
