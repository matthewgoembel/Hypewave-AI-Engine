// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyAsfzVbFX1hruEvnNSH5zx8ZmuOj0lVHZ8",
  authDomain: "hypewave-users.firebaseapp.com",
  projectId: "hypewave-users",
  storageBucket: "hypewave-users.firebasestorage.app",
  messagingSenderId: "415344757321",
  appId: "1:415344757321:web:5b2baa2ca798f75c740d98",
  measurementId: "G-1J2LVTG4WM"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);