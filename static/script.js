document.addEventListener("DOMContentLoaded", function () {
    const registerForm = document.getElementById("register-form");
    const loginForm = document.getElementById("login-form");
    const logoutBtn = document.getElementById("logout-btn");

    console.log("JavaScript загружен!");


    // Проверка токена при загрузке страницы
    checkAuth();

    // Регистрация пользователя
    if (registerForm) {
        registerForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            let username = document.getElementById("register-username").value;
            let password = document.getElementById("register-password").value;

            let response = await fetch("/auth/register", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username: username, password: password})
            });

            let result = await response.json();
            if (response.ok) {
                alert("Успешная регистрация!");
                loginUser(username, password);
            } else {
                alert("Ошибка: " + result.detail);
            }
        });
    }

    // Авторизация пользователя
    if (loginForm) {
        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            let username = document.getElementById("login-username").value;
            let password = document.getElementById("login-password").value;

            let response = await fetch("/auth/l ogin", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username: username, password: password})
            });


            let result = await response.json();
            if (response.ok) {
                localStorage.setItem("token", result.access_token);
                localStorage.setItem("username", username);
                window.location.href = "/chats.html";
            } else {
                alert("Ошибка: " + result.detail);
            }
        });
    }

    // Выход из системы
    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("token");
            localStorage.removeItem("username");
            window.location.href = "/index.html";
        });
    }

    // Проверка авторизации
    function checkAuth() {
        let token = localStorage.getItem("token");
        if (token) {
            document.getElementById("auth-section").style.display = "none";
            document.getElementById("chats-section").style.display = "block";
            loadChats();
        } else {
            document.getElementById("auth-section").style.display = "block";
            document.getElementById("chats-section").style.display = "none";
        }
    }

    // Загрузка списка чатов
    async function loadChats() {
        let token = localStorage.getItem("token");
        let response = await fetch("/chats", {
            method: "GET",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        let chats = await response.json();
        let chatList = document.getElementById("chat-list");
        chatList.innerHTML = "";

        chats.forEach(chat => {
            let li = document.createElement("li");
            li.textContent = chat.name;
            chatList.appendChild(li);
        });
    }
});
