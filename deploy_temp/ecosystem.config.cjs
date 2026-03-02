module.exports = {
    apps: [
        {
            name: "bot-agresivo-backend",
            script: "./start_backend.sh",
            cwd: "/home/daniel/proyectos/Bot_agresivo",
            watch: false,
            autorestart: true,
            max_memory_restart: '200M'
        }
    ]
};
