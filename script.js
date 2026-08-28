const authSection = document.getElementById("auth-section");
const appSection = document.getElementById("app-section");
const authUsername = document.getElementById("auth-username");
const authPassword = document.getElementById("auth-password");
const authMessage = document.getElementById("auth-message");
const loginButton = document.getElementById("login-button");
const registerButton = document.getElementById("register-button");
const logoutButton = document.getElementById("logout-button");
const currentUsernameSpan = document.getElementById("current-username");

const askButton = document.getElementById("ask-button");
const questionInput = document.getElementById("question");
const answerBox = document.getElementById("answer-box");

const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-button");
const uploadMessage = document.getElementById("upload-message");
const documentsList = document.getElementById("documents-list");

const API_URL = "http://127.0.0.1:8000";

function formatErrorDetail(detail) {
    if (typeof detail === "string") {
        return detail;
    }
    if (Array.isArray(detail)) {
        return detail.map(function (err) {
            // Pydantic errors look like: { loc: ["body", "username"], msg: "...", type: "..." }
            const field = err.loc && err.loc.length > 0 ? err.loc[err.loc.length - 1] : null;
            const label = field ? field.charAt(0).toUpperCase() + field.slice(1) : "Field";
            return `${label}: ${err.msg}`;
        }).join(" | ");
    }
    return "Something went wrong.";
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    return (bytes / 1024).toFixed(1) + " KB";
}

function showLoggedIn(username) {
    authSection.style.display = "none";
    appSection.style.display = "block";
    currentUsernameSpan.textContent = username;
    loadDocuments();
}

function showLoggedOut() {
    authSection.style.display = "block";
    appSection.style.display = "none";
}

async function loadDocuments() {
    const token = localStorage.getItem("token");

    try {
        const response = await fetch(`${API_URL}/documents`, {
            headers: { "Authorization": `Bearer ${token}` }
        });

        const data = await response.json();

        if (!response.ok) {
            documentsList.textContent = formatErrorDetail(data.detail);
            return;
        }

        if (data.documents.length === 0) {
            documentsList.textContent = "No documents uploaded yet.";
            return;
        }

        documentsList.innerHTML = "";

        for (const doc of data.documents) {
            const row = document.createElement("div");
            row.style.display = "flex";
            row.style.justifyContent = "space-between";
            row.style.alignItems = "center";
            row.style.padding = "6px 0";

            const label = document.createElement("span");
            label.textContent = `${doc.filename} — ${doc.chunks} chunks, ${formatSize(doc.size_bytes)}`;

            const deleteBtn = document.createElement("button");
            deleteBtn.textContent = "Delete";
            deleteBtn.addEventListener("click", function () {
                deleteDocument(doc.filename);
            });

            row.appendChild(label);
            row.appendChild(deleteBtn);
            documentsList.appendChild(row);
        }

    } catch (error) {
        documentsList.textContent = "Could not connect to the backend.";
        console.error(error);
    }
}

async function deleteDocument(filename) {
    const token = localStorage.getItem("token");

    try {
        const response = await fetch(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (!response.ok) {
            const data = await response.json();
            alert(formatErrorDetail(data.detail));
            return;
        }

        loadDocuments();

    } catch (error) {
        alert("Could not connect to the backend.");
        console.error(error);
    }
}

const savedToken = localStorage.getItem("token");
const savedUsername = localStorage.getItem("username");

if (savedToken && savedUsername) {
    showLoggedIn(savedUsername);
} else {
    showLoggedOut();
}

registerButton.addEventListener("click", async function () {
    const username = authUsername.value.trim();
    const password = authPassword.value;

    if (username.length < 3) {
        authMessage.textContent = "Username must be at least 3 characters.";
        return;
    }
    if (password.length < 6) {
        authMessage.textContent = "Password must be at least 6 characters.";
        return;
    }

    try {
        const response = await fetch(`${API_URL}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (!response.ok) {
            authMessage.textContent = formatErrorDetail(data.detail);
            return;
        }

        authMessage.textContent = "Account created! Now log in.";

    } catch (error) {
        authMessage.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});

loginButton.addEventListener("click", async function () {
    const username = authUsername.value.trim();
    const password = authPassword.value;

    if (username === "" || password === "") {
        authMessage.textContent = "Please enter both a username and password.";
        return;
    }

    try {
        const response = await fetch(`${API_URL}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (!response.ok) {
            authMessage.textContent = formatErrorDetail(data.detail);
            return;
        }

        localStorage.setItem("token", data.access_token);
        localStorage.setItem("username", username);

        showLoggedIn(username);

    } catch (error) {
        authMessage.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});

logoutButton.addEventListener("click", function () {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    showLoggedOut();
});

askButton.addEventListener("click", async function () {
    const question = questionInput.value.trim();
    if (question === "") {
        answerBox.textContent = "Please enter a question.";
        return;
    }
    const token = localStorage.getItem("token");
    answerBox.textContent = "Thinking...";

    try {
        const response = await fetch(`${API_URL}/ask`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ question: question })
        });

        if (response.status === 401) {
            answerBox.textContent = "";
            authMessage.textContent = "Your session expired, please log in again.";
            localStorage.removeItem("token");
            localStorage.removeItem("username");
            showLoggedOut();
            return;
        }

        const data = await response.json();

        if (!response.ok) {
            answerBox.textContent = formatErrorDetail(data.detail);
            return;
        }

        answerBox.innerHTML = `
            <p>${data.answer}</p>
            <p><em>Sources: ${data.sources.join(", ")}</em></p>
        `;

    } catch (error) {
        answerBox.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});

uploadButton.addEventListener("click", async function () {
    const file = fileInput.files[0];

    if (!file) {
        uploadMessage.textContent = "Choose a file first.";
        return;
    }

    const token = localStorage.getItem("token");
    const formData = new FormData();
    formData.append("file", file);

    uploadMessage.textContent = "Uploading...";

    try {
        const response = await fetch(`${API_URL}/documents/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            uploadMessage.textContent = formatErrorDetail(data.detail);
            return;
        }

        uploadMessage.textContent = `Uploaded "${data.filename}" (${data.total_chunks} chunks total).`;
        fileInput.value = "";
        loadDocuments();

    } catch (error) {
        uploadMessage.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});