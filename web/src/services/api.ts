import axios from 'axios';

const API_BASE = '/api';

export const botService = {
    async getRole() {
        const response = await axios.get(`${API_BASE}/role`);
        return response.data.role;
    },

    async getState() {
        const response = await axios.get(`${API_BASE}/state`);
        return response.data;
    },

    async controlBot(strategyId: string, action: string) {
        const response = await axios.post(`${API_BASE}/control/${strategyId}/${action}`);
        return response.data;
    }
};
