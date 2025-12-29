#Requires AutoHotkey v2.0
#SingleInstance Force
; To test:
; curl.exe -X POST "http://127.0.0.1:9181/alert" -H "Content-Type: application/json" -d "{\"message\":\"Task feedback needed\"}"

port := 9181
server := HttpServer(port)
MsgBox("Alert server running on http://localhost:" port "/alert")

class HttpServer {
    __New(port) {
        this.port := port

        this.StartWSA()

        this.sock := DllCall("Ws2_32\socket", "int", 2, "int", 1, "int", 6, "ptr") ; AF_INET, SOCK_STREAM, IPPROTO_TCP
        if (this.sock = -1)
            throw Error("socket failed")

        ; optional: allow fast restart after close
        opt := Buffer(4, 0)
        NumPut("int", 1, opt, 0)
        DllCall("Ws2_32\setsockopt", "ptr", this.sock, "int", 0xFFFF, "int", 0x0004, "ptr", opt.Ptr, "int", 4) ; SOL_SOCKET=0xFFFF, SO_REUSEADDR=4

        this.Bind()
        this.Listen()

        this.timer := ObjBindMethod(this, "Accept")
        SetTimer(this.timer, 50)
    }

    StartWSA() {
        static wsaStarted := false
        if wsaStarted
            return
        wsa := Buffer(32, 0)
        if DllCall("Ws2_32\WSAStartup", "ushort", 0x0202, "ptr", wsa.Ptr)
            throw Error("WSAStartup failed")
        wsaStarted := true
    }

    Bind() {
        addr := Buffer(16, 0) ; sockaddr_in
        NumPut("ushort", 2, addr, 0) ; AF_INET
        NumPut("ushort", DllCall("Ws2_32\htons", "ushort", this.port, "ushort"), addr, 2)
        NumPut("uint", 0, addr, 4) ; INADDR_ANY

        if DllCall("Ws2_32\bind", "ptr", this.sock, "ptr", addr.Ptr, "int", 16)
            throw Error("bind failed (port in use? permissions?)")
    }

    Listen() {
        if DllCall("Ws2_32\listen", "ptr", this.sock, "int", 10)
            throw Error("listen failed")
    }

    Accept() {
        client := DllCall("Ws2_32\accept", "ptr", this.sock, "ptr", 0, "ptr", 0, "ptr")
        if (client = -1)
            return

        req := this.ReadAll(client)

        if InStr(req, "POST /alert") {
            body := this.GetBody(req)
            msg := this.ExtractMessage(body)
            ShowCenteredAlert(msg != "" ? msg : "Task feedback needed")
            this.Send(client, "HTTP/1.1 200 OK`r`nContent-Type: text/plain`r`nConnection: close`r`n`r`nOK")
        } else {
            this.Send(client, "HTTP/1.1 404 Not Found`r`nContent-Type: text/plain`r`nConnection: close`r`n`r`nNot Found")
        }

        DllCall("Ws2_32\closesocket", "ptr", client)
    }

    ReadAll(sock) {
        buf := Buffer(8192, 0)
        received := DllCall("Ws2_32\recv", "ptr", sock, "ptr", buf.Ptr, "int", buf.Size, "int", 0)
        if (received <= 0)
            return ""
        return StrGet(buf.Ptr, received, "UTF-8")
    }

    GetBody(req) {
        parts := StrSplit(req, "`r`n`r`n", , 2)
        return (parts.Length >= 2) ? parts[2] : ""
    }

    ExtractMessage(body) {
        ; URL-encoded form: message=...
        if RegExMatch(body, "message=([^&]+)", &m)
            return UriDecode(m[1])

        ; JSON: {"message":"..."}  (simple)
        if RegExMatch(body, '"message"\s*:\s*"([^"]*)"', &m)
            return m[1]

        return Trim(body)
    }

    Send(sock, text) {
        bytes := StrPut(text, "UTF-8") ; includes null
        tmp := Buffer(bytes, 0)
        StrPut(text, tmp, "UTF-8")
        DllCall("Ws2_32\send", "ptr", sock, "ptr", tmp.Ptr, "int", bytes - 1, "int", 0)
    }
}

ShowCenteredAlert(msg) {
    gui := Gui("+AlwaysOnTop -Caption +ToolWindow")
    gui.BackColor := "20232a"
    gui.SetFont("s14 cFFFFFF", "Segoe UI")
    gui.Add("Text", "w420 h70 Center", msg)

    MonitorGetWorkArea(1, &L, &T, &R, &B)
    x := L + (R - L - 420) // 2
    y := T + (B - T - 70) // 2

    gui.Show("x" x " y" y " w420 h70")
    SetTimer(() => gui.Destroy(), -4000)
}

UriDecode(str) {
    ; convert + to space, and %XX to character
    str := StrReplace(str, "+", " ")
    return RegExReplace(str, "\%([0-9A-Fa-f]{2})", (m) => Chr("0x" m[1]))
}
