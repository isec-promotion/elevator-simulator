// elevator_enq_sim.c
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <signal.h>

static HANDLE hSerial = INVALID_HANDLE_VALUE;
static volatile int running = 1;

// シグナルハンドラー
void sigint_handler(int sig) {
    printf("\n🛑 シグナル %d を受信しました。終了処理中...\n", sig);
    running = 0;
}

// 階数→文字列
const char* floor_to_string(int floor) {
    switch (floor) {
        case -1: return "B1F";
        case  1: return "1F";
        case  2: return "2F";
        case  3: return "3F";
        default: return "?";
    }
}

// シリアルポート初期化
int init_serial(const wchar_t* portName) {
    hSerial = CreateFileW(portName,
                          GENERIC_READ|GENERIC_WRITE,
                          0, NULL,
                          OPEN_EXISTING,
                          FILE_ATTRIBUTE_NORMAL,
                          NULL);
    if (hSerial == INVALID_HANDLE_VALUE) {
        fwprintf(stderr, L"❌ シリアルポート %ls を開けません: エラーコード %lu\n",
                 portName, GetLastError());
        return 0;
    }
    DCB dcb = {0};
    dcb.DCBlength = sizeof(dcb);
    if (!GetCommState(hSerial, &dcb)) {
        fwprintf(stderr, L"❌ GetCommState 失敗: %lu\n", GetLastError());
        return 0;
    }
    dcb.BaudRate = CBR_9600;
    dcb.ByteSize = 8;
    dcb.Parity   = EVENPARITY;
    dcb.StopBits = ONESTOPBIT;
    if (!SetCommState(hSerial, &dcb)) {
        fwprintf(stderr, L"❌ SetCommState 失敗: %lu\n", GetLastError());
        return 0;
    }
    COMMTIMEOUTS timeouts = {0};
    timeouts.ReadIntervalTimeout         = 50;
    timeouts.ReadTotalTimeoutConstant    = 50;
    timeouts.ReadTotalTimeoutMultiplier  = 10;
    timeouts.WriteTotalTimeoutConstant   = 50;
    timeouts.WriteTotalTimeoutMultiplier = 10;
    SetCommTimeouts(hSerial, &timeouts);
    wprintf(L"✅ シリアルポート %ls 接続成功\n", portName);
    return 1;
}

// チェックサム計算
void calculate_checksum(const char* data, char* out) {
    unsigned int sum = 0;
    while (*data) sum += (unsigned char)*data++;
    sprintf(out, "%02X", sum & 0xFF);
}

// 階数→HEX
void floor_to_hex(int floor, char* out) {
    if (floor == -1) strcpy(out, "FFFF");
    else sprintf(out, "%04X", floor);
}

// 現在時刻文字列取得
void current_time_str(char* buf, size_t len) {
    time_t t = time(NULL);
    struct tm lt;
    localtime_s(&lt, &t);
    strftime(buf, len, "%Y年%m月%d日 %H:%M:%S", &lt);
}

// ENQ送信
void send_enq(const char* dataNum, const char* dataValue, const char* desc) {
    const char* station = "0002";
    const char* cmd = "W";
    char data_part[64], checksum[3], message[80];
    sprintf(data_part, "%s%s%s%s", station, cmd, dataNum, dataValue);
    calculate_checksum(data_part, checksum);
    sprintf(message, "\x05%s%s", data_part, checksum);
    DWORD written;
    if (!WriteFile(hSerial, message, (DWORD)strlen(message), &written, NULL)) {
        fprintf(stderr, "❌ ENQ送信エラー: %lu\n", GetLastError());
        return;
    }
    char ts[32];
    current_time_str(ts, sizeof(ts));
    printf("[%s] 📤 ENQ送信: %s (局番号:%s データ:%s チェック:%s)\n",
           ts, desc, station, dataValue, checksum);
}

// エントリポイント
int wmain(int argc, wchar_t* argv[]) {
    // コンソールを UTF-8 モード、VT 処理オン
    SetConsoleOutputCP(CP_UTF8);
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD mode = 0;
    if (GetConsoleMode(hOut, &mode)) {
        SetConsoleMode(hOut, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
    }

    // ポート名取得・自動補完
    wchar_t fullPort[64];
    if (argc >= 2) {
        if (wcsncmp(argv[1], L"\\\\.\\", 4) == 0) {
            wcscpy(fullPort, argv[1]);
        } else {
            swprintf(fullPort, 64, L"\\\\.\\%ls", argv[1]);
        }
    } else {
        wcscpy(fullPort, L"\\\\.\\COM31");
    }
    const wchar_t* portW = fullPort;
    int start_floor = (argc >= 3 ? _wtoi(argv[2]) : 1);

    signal(SIGINT, sigint_handler);
    signal(SIGTERM, sigint_handler);

    printf("🏢 エレベーターENQシミュレーター初期化\n");
    wprintf(L"📡 シリアルポート: %ls\n", portW);
    if (!init_serial(portW)) return 1;

    int floors[] = { -1, 1, 2, 3 };
    int num_floors = sizeof(floors)/sizeof(floors[0]);
    int current_floor = start_floor;

    srand((unsigned)time(NULL));

    printf("🏢 開始階数: %s\n", floor_to_string(current_floor));
    printf("🚀 シミュレーション開始 (Ctrl+C で終了)\n");
    printf("📋 仕様: ①現在階→②行先階→③乗客降客→10秒→④着床\n");

    while (running) {
        // 行先選択
        int target_floor;
        do {
            target_floor = floors[rand() % num_floors];
        } while (target_floor == current_floor);

        char cur_s[4], tgt_s[4];
        strcpy(cur_s, floor_to_string(current_floor));
        strcpy(tgt_s, floor_to_string(target_floor));
        printf("\n🎯 シナリオ: %s → %s\n", cur_s, tgt_s);

        // ①現在階送信×5
        char cur_hex[5]; floor_to_hex(current_floor, cur_hex);
        for (int i = 0; i < 5 && running; i++) {
            char desc[32]; sprintf(desc, "現在階: %s (%d/5)", cur_s, i+1);
            send_enq("0001", cur_hex, desc);
            Sleep(1000);
        }
        if (!running) break;
        printf("⏰ 3秒待機中...\n"); Sleep(3000);

        // ②行先階送信×5
        char tgt_hex[5]; floor_to_hex(target_floor, tgt_hex);
        for (int i = 0; i < 5 && running; i++) {
            char desc[32]; sprintf(desc, "行先階: %s (%d/5)", tgt_s, i+1);
            send_enq("0002", tgt_hex, desc);
            Sleep(1000);
        }
        if (!running) break;
        printf("⏰ 3秒待機中...\n"); Sleep(3000);

        // ③乗客降客送信×5
        for (int i = 0; i < 5 && running; i++) {
            char desc[32]; sprintf(desc, "乗客降客: 1870kg (%d/5)", i+1);
            send_enq("0003", "074E", desc);
            Sleep(1000);
        }
        if (!running) break;

        // 10秒待機
        printf("⏰ 10秒待機中...\n");
        for (int i = 0; i < 10 && running; i++) Sleep(1000);
        if (!running) break;

        // ④着床送信×5
        for (int i = 0; i < 5 && running; i++) {
            char desc[32]; sprintf(desc, "着床: クリア (%d/5)", i+1);
            send_enq("0002", "0000", desc);
            Sleep(1000);
        }
        current_floor = target_floor;
        printf("🏁 着床完了: %s\n", tgt_s);

        printf("⏰ 10秒待機中...\n");
        for (int i = 0; i < 10 && running; i++) Sleep(1000);
    }

    if (hSerial != INVALID_HANDLE_VALUE) {
        CloseHandle(hSerial);
        printf("📡 シリアルポート切断完了\n");
    }
    printf("🛑 シミュレーション終了\n");
    return 0;
}
