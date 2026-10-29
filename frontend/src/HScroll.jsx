import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronIcon } from './icons';

const DRAG_THRESHOLD = 4;

export default function HScroll({ children }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [edge, setEdge] = useState({ left: false, right: false });
  const [dragging, setDragging] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setEdge({ left: el.scrollLeft > 2, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 });
  }, []);

  useEffect(() => {
    update();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [update, children]);

  useEffect(() => {
    const move = (e) => {
      const d = drag.current;
      if (!d) return;
      const dx = e.clientX - d.x;
      if (Math.abs(dx) > DRAG_THRESHOLD) {
        d.moved = true;
        setDragging(true);
      }
      if (d.moved) ref.current.scrollLeft = d.left - dx;
    };
    const up = () => {
      if (!drag.current) return;
      setDragging(false);
      setTimeout(() => {
        drag.current = null;
      }, 0);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, []);

  const scrollBy = (dir) => ref.current.scrollBy({ left: dir * ref.current.clientWidth * 0.7, behavior: 'smooth' });

  return (
    <div className="hscroll">
      {edge.left && (
        <button type="button" className="hscroll-arrow left" aria-label="Прокрутить влево" onClick={() => scrollBy(-1)}>
          <ChevronIcon />
        </button>
      )}
      <div
        ref={ref}
        className={dragging ? 'hscroll-track dragging' : 'hscroll-track'}
        onScroll={update}
        onMouseDown={(e) => {
          if (e.button === 0) drag.current = { x: e.clientX, left: ref.current.scrollLeft, moved: false };
        }}
        onClickCapture={(e) => {
          if (drag.current?.moved) {
            e.stopPropagation();
            e.preventDefault();
          }
        }}
      >
        {children}
      </div>
      {edge.right && (
        <button type="button" className="hscroll-arrow right" aria-label="Прокрутить вправо" onClick={() => scrollBy(1)}>
          <ChevronIcon />
        </button>
      )}
    </div>
  );
}
