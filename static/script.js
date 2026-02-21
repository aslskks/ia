let currentChat = localStorage.getItem("currentChat") || null
let mediaRecorder;
let audioChunks = [];
let stream;
let isRecording = false;

const voiceBtn = document.getElementById("voiceBtn");

async function toggleRecording() {
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
}

async function startRecording() {

    try {

        stream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        const mimeType = MediaRecorder.isTypeSupported("audio/webm")
            ? "audio/webm"
            : "audio/ogg";

mediaRecorder = new MediaRecorder(stream, {
    mimeType: mimeType,
    audioBitsPerSecond: 128000
});

        audioChunks = [];

        voiceBtn.classList.add("recording");

        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) {
                audioChunks.push(e.data);
            }
        };

        mediaRecorder.onstop = async () => {

            const blob = new Blob(audioChunks, {
                type: mimeType
            });

            await sendAudioToServer(blob, mimeType);

        };

        mediaRecorder.start();

        isRecording = true;

    }
    catch (err) {
        console.error(err);
    }
}

function stopRecording() {

    mediaRecorder.stop();

    stream.getTracks().forEach(track => track.stop());

    voiceBtn.classList.remove("recording");

    isRecording = false;
}

async function sendAudioToServer(blob, mimeType) {

    const formData = new FormData();

    const respo = await fetch("/uuid");
    const user = await respo.json();

    const ext = mimeType.includes("webm") ? "webm" : "ogg";

    formData.append("audio", blob, `voice/${user.uuid}.${ext}`);

    const res = await fetch("/speech_to_text", {
        method: "POST",
        body: formData
    });

    const data = await res.json();

console.log("Respuesta completa:", data);
console.log("Texto:", data.text);


    if (data.text) {
        document.getElementById("input").value = data.text;
        sendMessage();
    }
}

function escapeHtml(text) {

    return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
}

function renderMessage(role, content) {

    const messages = document.getElementById("messages")

    const container = document.createElement("div")
    container.className = "message " + role

    const avatar = document.createElement("div")
    avatar.className = "avatar"

    avatar.innerText =
        role === "user"
        ? document.getElementById("userAvatar").innerText
        : "AI"
    const bubble = document.createElement("div")
    bubble.className = "bubble"
    bubble.innerHTML = formatMessage(content)
    if (role === "user") {
        container.appendChild(bubble)
        container.appendChild(avatar)
    }

    else {

        container.appendChild(avatar)
        container.appendChild(bubble)

    }

    messages.appendChild(container)
    container.offsetHeight
    scrollBottom()
}



async function loadUser() {

    const res = await fetch("/me")
    const user = await res.json()

    document.getElementById("username").innerText = user.name
    document.getElementById("userEmail").innerText = user.email

    currentUserAvatar = user.name.charAt(0).toUpperCase()

    document.getElementById("userAvatar").innerText =
        currentUserAvatar
}


loadUser()



function renderWritingIndicator() {

    const container = document.createElement("div")
    container.className = "message assistant"

    container.id = "writingBubble"

container.innerHTML = `
<div id="writingIndicator" class="writing-indicator">
    writing<span id="dots"></span>
</div>
`


    document.getElementById("messages").appendChild(container)

    scrollBottom()
}
const textarea = document.getElementById("input")

textarea.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
    }
})
textarea.addEventListener("input", function() {

    this.style.height = "auto"
    this.style.height = this.scrollHeight + "px"

})
function removeWritingIndicator() {

    const el = document.getElementById("writingBubble")

    if(el) el.remove()
}

function scrollBottom() {
    const m = document.getElementById("messages")
    m.scrollTop = m.scrollHeight
}
function formatMessage(text){

    if(!text) return ""

    /* SANDBOX */
    text = text.replace(
        /\[SANDBOX OUTPUT\]\n?([\s\S]*?)(?=\n|$)/gi,
        (m, out)=>{
            return `<div class="sandbox-output">${escapeHtml(out)}</div>`
        }
    )

    /* BLOCKS */
    const blocks = []

    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g,(match,lang,code)=>{
        const id = blocks.length

        blocks.push({
            lang: lang || "code",
            code: escapeHtml(code)
        })

        return `@@CODEBLOCK_${id}@@`
    })

    /* INLINE ESCAPE */
    text = escapeHtml(text)

    /* INLINE MD */
    text = text.replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>")
    text = text.replace(/\*(.*?)\*/g,"<em>$1</em>")
    text = text.replace(/`([^`]+)`/g,"<code>$1</code>")
    text = text.replace(/(https?:\/\/[^\s]+)/g,`<a href="$1" target="_blank">$1</a>`)
    text = text.replace(/\n/g,"<br>")

    /* RESTORE */
    blocks.forEach((b,i)=>{

const html = `
<div class="code-wrapper">
  <div class="code-header">
    <span>${b.lang}</span>

    <div class="code-actions">
        <button class="run-code-btn" onclick="runCode(this)">Run</button>
        <button class="copy-code-btn" onclick="copyCode(this)">Copy</button>
    </div>
  </div>

  <pre class="code-block"><code>${b.code}</code></pre>

  <div class="code-output"></div>
</div>
`
        text = text.replace(`@@CODEBLOCK_${i}@@`, html)
    })

    return text || ""
}
async function runCode(btn){

    const wrapper = btn.closest(".code-wrapper")
    if(!wrapper) return

    const code = wrapper.querySelector("code")?.innerText || ""
    const output = wrapper.querySelector(".code-output")

    btn.classList.add("running")
    btn.innerText = "Running..."
    output.innerText = "Executing..."

    try{

        const res = await fetch("/run_block",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({
                code,
                chat_id: currentChat
            })
        })

        const data = await res.json()

        output.innerText = data.output || data.error || "Done"
        showDownloads(data)

    }catch(e){
        console.error(e)
        output.innerText = "Execution failed"
    }

    btn.classList.remove("running")
    btn.innerText = "Run"
}
document.addEventListener("dragenter", ()=>{
    if(!document.querySelector(".drop-overlay")){
        const o=document.createElement("div")
        o.className="drop-overlay"
        o.innerText="Drop file to upload"
        document.body.appendChild(o)
    }
})
function showDownloads(data){

    if(!data.files || !data.files.length) return

    const list = document.getElementById("downloadList")
    list.innerHTML = ""

    data.files.forEach(file=>{
        const a = document.createElement("a")
        a.href = `/download/${data.uuid}/${file}`
        a.innerText = "⬇ " + file
        a.target = "_blank"
        a.className = "download-btn"
        list.appendChild(a)
    })

    document.getElementById("downloadOverlay").classList.add("show")
}
function closeDownload(){
    document.getElementById("downloadOverlay").classList.remove("show")
}
document.addEventListener("dragleave", ()=>{
    document.querySelector(".drop-overlay")?.remove()
})

document.addEventListener("drop", ()=>{
    document.querySelector(".drop-overlay")?.remove()
})
async function sendMessage() {

    const input = document.getElementById("input")
    const text = input.value.trim()
    if (!text) return

    renderMessage("user", text)
    input.value = ""
    renderWritingIndicator()

    let reader
    let fullText = ""
    let buffer = ""

    try {

        const res = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                message: text,
                chat_id: currentChat,   // ⭐ ENVIA CHAT ACTUAL
                stream: true
            })
        })

        reader = res.body.getReader()
        const decoder = new TextDecoder()

        removeWritingIndicator()

        /* =========================
           CREATE ASSISTANT BUBBLE
        ========================= */

        const container = document.createElement("div")
        container.className = "message assistant"

        const avatar = document.createElement("div")
        avatar.className = "avatar"
        avatar.innerText = "AI"

        const bubble = document.createElement("div")
        bubble.className = "bubble streaming"

        container.appendChild(avatar)
        container.appendChild(bubble)
        document.getElementById("messages").appendChild(container)

        bubble.innerHTML = "&nbsp;"

        /* =========================
           STREAM LOOP
        ========================= */

        while (true) {

            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })

            let lines = buffer.split("\n")
            buffer = lines.pop()

            for (const line of lines) {

                if (!line.trim()) continue

                const data = JSON.parse(line)

                /* ⭐ CAPTURAR CHAT ID */
                if (data.chat_id) {
                    currentChat = data.chat_id
                    localStorage.setItem("currentChat", currentChat)
                }

                /* ⭐ STREAM TOKEN */
                if (data.token) {
                    fullText += data.token
                    bubble.innerHTML = formatMessage(fullText)
                    scrollBottom()
                }
            }
        }

        bubble.classList.remove("streaming")
        loadChats()

    } catch (err) {

        console.error(err)
        removeWritingIndicator()

        if (!fullText.trim()) {
            renderMessage("assistant", "Error: connection failed")
        }
    }
}


function newChat(){
    currentChat = null
    localStorage.removeItem("currentChat")
    clearMessages()
}
async function loadChats() {

    const res = await fetch("/get_chats")
    const chats = await res.json()

    const list = document.getElementById("chatList")

    if (!list) {
        console.error("chatList no existe")
        return
    }

    list.innerHTML = ""

    for (const id in chats) {

        const div = document.createElement("div")
        div.className = "chat-item"

        if (id === currentChat)
            div.classList.add("active")

        div.onclick = function() {
            loadChat(id)
        }

        const title = document.createElement("div")
        title.innerText = chats[id].title

        const menuBtn = document.createElement("button")
        menuBtn.className = "chat-menu-btn"
        menuBtn.innerText = "⋯"

        menuBtn.onclick = function(e) {
            e.stopPropagation()
            toggleChatMenu(id, menuBtn)
        }

        div.appendChild(title)
        div.appendChild(menuBtn)

        list.appendChild(div)
    }
}


async function loadChat(chat_id) {

    currentChat = chat_id

    const res = await fetch("/messages/" + chat_id)

    const data = await res.json()

    const messages = document.getElementById("messages")

    messages.innerHTML = ""

    for (const msg of data) {

        renderMessage(msg.role, msg.content)

    }

}



loadChats()

let openMenu = null

function toggleChatMenu(chatId, btn) {

    closeMenu()

    const menu = document.createElement("div")
    menu.className = "chat-menu"

    menu.innerHTML = `
        <div class="chat-menu-item" onclick="renameChat('${chatId}')">Rename</div>
        <div class="chat-menu-item delete" onclick="deleteChat('${chatId}')">Delete</div>
    `

    document.body.appendChild(menu)

    const rect = btn.getBoundingClientRect()

    menu.style.top = rect.bottom + "px"
    menu.style.left = rect.left + "px"

    openMenu = menu

    setTimeout(() => {
        document.addEventListener("click", closeMenuOnce)
    }, 0)
}

function closeMenuOnce() {
    closeMenu()
    document.removeEventListener("click", closeMenuOnce)
}

function closeMenu() {
    if (openMenu) {
        openMenu.remove()
        openMenu = null
    }
}

async function renameChat(chatId) {

    const newName = prompt("New chat name:")

    if (!newName) return

    await fetch("/rename_chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            chat_id: chatId,
            title: newName
        })
    })

    loadChats()
}

async function deleteChat(chatId) {

    await fetch("/delete_chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            chat_id: chatId
        })
    })

    if (chatId === currentChat) {
        currentChat = null
        document.getElementById("messages").innerHTML = ""
    }

    loadChats()
}
let userMenu = null

function toggleUserMenu(event){

    event.stopPropagation();

    let old = document.querySelector(".user-menu");

    if(old){
        old.remove();
        return;
    }

    const menu = document.createElement("div");
    menu.className = "user-menu";

    menu.innerHTML = `
        <div class="user-menu-item" onclick="clearAllChats()">
            Clear conversations
        </div>

        <div class="user-menu-divider"></div>

        <div class="user-menu-item danger" onclick="logout()">
            🚪 Log out
        </div>
    `;

    document.body.appendChild(menu);

    const rect = event.currentTarget.getBoundingClientRect();

    menu.style.left = rect.left + "px";
    menu.style.top = (rect.top - menu.offsetHeight - 10) + "px";
}
document.addEventListener("click", function(){

    const menu = document.querySelector(".user-menu");

    if(menu) menu.remove();

});


function closeUserMenu() {

    if (userMenu) {

        userMenu.remove()
        userMenu = null

        document.removeEventListener("click", closeUserMenu)
    }

}

fetch("/me")
.then(r => r.json())
.then(user => {

    document.getElementById("username").innerText = user.name
    document.getElementById("userEmail").innerText = user.email
    document.getElementById("userAvatar").innerText =
        user.name.charAt(0).toUpperCase()

})

function logout() {
    location.href = "/logout"
}
function closeUserMenuOnce() {
    closeUserMenu()
    document.removeEventListener("click", closeUserMenuOnce)
}

function closeUserMenu() {

    if (userMenu) {
        userMenu.remove()
        userMenu = null
    }
}
async function clearAllChats() {

    if (!confirm("Delete all chats?")) return

    await fetch("/delete_all_chats", {
        method: "POST"
    })

    currentChat = null

    document.getElementById("messages").innerHTML = ""

    loadChats()
}
function selectUser() {

    location.href = "/select_user"
}