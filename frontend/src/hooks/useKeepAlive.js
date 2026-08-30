import { useEffect } from 'react';
import { getEndpoint } from '../config/backend';

const NINE_MINUTES = 9 * 60 * 1000;

export const useKeepAlive = () => {
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(getEndpoint('/ping/')).catch(() => {});
    }, NINE_MINUTES);

    return () => clearInterval(interval);
  }, []);
};
