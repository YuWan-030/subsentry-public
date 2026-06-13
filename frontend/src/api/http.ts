import axios from "axios";

const configuredBaseURL = import.meta.env.VITE_API_BASE_URL || "";
const isLocalBaseURL = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(configuredBaseURL);
const baseURL = import.meta.env.PROD && isLocalBaseURL ? "" : configuredBaseURL;

const api = axios.create({
  baseURL,
  withCredentials: true,
});

api.interceptors.response.use(
  (response) => {
    const data = response.data;
    if (data && typeof data === "object" && "success" in data && data.success === false) {
      const error = new Error(
        data.detail || data.message || data.msg || "Request failed"
      ) as Error & {
        response?: typeof response;
      };
      error.response = response;
      return Promise.reject(error);
    }
    return response;
  },
  (error) => {
    const responseData = error?.response?.data;
    const normalizedMessage =
      responseData?.detail ||
      responseData?.message ||
      responseData?.msg ||
      error?.message ||
      "Network request failed";

    if (responseData && typeof responseData === "object") {
      if (!responseData.detail) {
        responseData.detail = normalizedMessage;
      }
      if (!responseData.message) {
        responseData.message = normalizedMessage;
      }
    }

    error.message = normalizedMessage;
    return Promise.reject(error);
  }
);

export default api;
