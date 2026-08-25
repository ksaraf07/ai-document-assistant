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

const API_URL = "http://127.0.0.1:8000";

function showLoggedIn(username) {
    authSection.style.display = "none";
    appSection.style.display = "block";
    currentUsernameSpan.textContent = username;
}

function showLoggedOut() {
    authSection.style.display = "block";
    appSection.style.display = "none";
}

const savedToken = localStorage.getItem("token");
const savedUsername = localStorage.getItem("username");

if (savedToken && savedUsername) {
    showLoggedIn(savedUsername);
} else {
    showLoggedOut();
}

function formatErrorDetail(detail) {
    if (typeof detail === "string") {
        return detail;
    }
    if (Array.isArray(detail)) {
        return detail.map(function (err) { return err.msg; }).join(", ");
    }
    return "Something went wrong.";
}

registerButton.addEventListener("click", async function () {
    const username = authUsername.value;
    const password = authPassword.value;

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
    const username = authUsername.value;
    const password = authPassword.value;

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
    const question = questionInput.value;
    if (question === "") return;

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

        answerBox.innerHTML = `
            <p>${data.answer}</p>
            <p><em>Sources: ${data.sources.join(", ")}</em></p>
        `;

    } catch (error) {
        answerBox.textContent = "Could not connect to the backend.";
        console.error(error);
    }
});