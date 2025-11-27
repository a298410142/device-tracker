import React, { useState, useEffect, useRef } from 'react';
import { Camera, Save, RotateCcw, History, Phone, User, Trash2, XCircle, CheckCircle, Package, AlertCircle } from 'lucide-react';

export default function App() {
  // 應用程式狀態
  const [activeTab, setActiveTab] = useState('borrow'); // borrow, active, history
  const [borrowedItems, setBorrowedItems] = useState([]);
  const [historyItems, setHistoryItems] = useState([]);
  
  // 表單狀態
  const [formData, setFormData] = useState({
    name: '',
    extension: '',
    photo: null
  });
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [isCompressing, setIsCompressing] = useState(false);

  // 確認視窗狀態 (取代 window.confirm)
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    type: null, // 'return' or 'delete'
    itemId: null,
    title: '',
    message: ''
  });
  
  const fileInputRef = useRef(null);

  // 初始化：從 LocalStorage 讀取資料
  useEffect(() => {
    const savedBorrowed = localStorage.getItem('device_tracker_borrowed');
    const savedHistory = localStorage.getItem('device_tracker_history');
    if (savedBorrowed) setBorrowedItems(JSON.parse(savedBorrowed));
    if (savedHistory) setHistoryItems(JSON.parse(savedHistory));
  }, []);

  // 當資料變更時，存入 LocalStorage
  useEffect(() => {
    localStorage.setItem('device_tracker_borrowed', JSON.stringify(borrowedItems));
  }, [borrowedItems]);

  useEffect(() => {
    localStorage.setItem('device_tracker_history', JSON.stringify(historyItems));
  }, [historyItems]);

  // 圖片處理：壓縮並轉為黑白
  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsCompressing(true);
    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        const maxWidth = 600;
        let width = img.width;
        let height = img.height;

        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }

        canvas.width = width;
        canvas.height = height;

        ctx.drawImage(img, 0, 0, width, height);

        const imageData = ctx.getImageData(0, 0, width, height);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {
          const avg = (data[i] + data[i + 1] + data[i + 2]) / 3;
          data[i] = avg;
          data[i + 1] = avg;
          data[i + 2] = avg;
        }
        ctx.putImageData(imageData, 0, 0);

        const compressedBase64 = canvas.toDataURL('image/jpeg', 0.6);
        
        setFormData(prev => ({ ...prev, photo: compressedBase64 }));
        setIsCompressing(false);
      };
      img.src = event.target.result;
    };
    reader.readAsDataURL(file);
  };

  // 提交借用表單
  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!formData.name.trim() && !formData.extension.trim()) {
      setError('請至少輸入「姓名」或「分機」其中一項。');
      return;
    }

    if (!formData.photo) {
      setError('請拍攝設備照片。');
      return;
    }

    const newItem = {
      id: Date.now(),
      date: new Date().toLocaleString('zh-TW', { hour12: false }),
      ...formData
    };

    setBorrowedItems([newItem, ...borrowedItems]);
    setFormData({ name: '', extension: '', photo: null });
    setSuccessMsg('借用登記成功！');
    
    setTimeout(() => {
        setSuccessMsg('');
        setActiveTab('active');
    }, 1500);
  };

  // 開啟歸還確認視窗
  const openReturnModal = (id) => {
    setConfirmModal({
      isOpen: true,
      type: 'return',
      itemId: id,
      title: '歸還確認',
      message: '確定要歸還此設備嗎？這將會把紀錄移至歷史區。'
    });
  };

  // 開啟刪除確認視窗
  const openDeleteModal = (id) => {
    setConfirmModal({
      isOpen: true,
      type: 'delete',
      itemId: id,
      title: '刪除確認',
      message: '確定要刪除這筆歷史紀錄嗎？此動作無法復原。'
    });
  };

  // 執行確認動作
  const executeConfirmAction = () => {
    const { type, itemId } = confirmModal;

    if (type === 'return') {
      const itemToReturn = borrowedItems.find(item => item.id === itemId);
      if (itemToReturn) {
        const returnRecord = {
          ...itemToReturn,
          returnDate: new Date().toLocaleString('zh-TW', { hour12: false })
        };
        setHistoryItems([returnRecord, ...historyItems]);
        setBorrowedItems(borrowedItems.filter(item => item.id !== itemId));
      }
    } else if (type === 'delete') {
      setHistoryItems(historyItems.filter(item => item.id !== itemId));
    }

    // 關閉視窗
    setConfirmModal({ isOpen: false, type: null, itemId: null, title: '', message: '' });
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800 font-sans pb-24 relative">
      {/* 頂部標題 */}
      <header className="bg-blue-600 text-white p-4 shadow-md sticky top-0 z-10">
        <h1 className="text-xl font-bold text-center flex items-center justify-center gap-2">
          <Package size={24} />
          設備登記系統
        </h1>
      </header>

      <main className="max-w-md mx-auto p-4">
        
        {/* === 借用登記表單 === */}
        {activeTab === 'borrow' && (
          <div className="space-y-6 animate-fade-in">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
              <h2 className="text-lg font-semibold mb-4 text-gray-700 flex items-center gap-2">
                <Camera className="text-blue-500" /> 新增借用
              </h2>

              <div 
                className="mb-6 border-2 border-dashed border-gray-300 rounded-lg p-4 text-center cursor-pointer hover:bg-gray-50 transition-colors relative"
                onClick={() => fileInputRef.current.click()}
              >
                {formData.photo ? (
                  <div className="relative">
                    <img src={formData.photo} alt="Device" className="mx-auto max-h-48 rounded shadow-sm filter grayscale" />
                    <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
                      已轉黑白壓縮
                    </div>
                  </div>
                ) : (
                  <div className="py-8 flex flex-col items-center text-gray-400">
                    <Camera size={48} className="mb-2" />
                    <span>點擊拍攝設備照片</span>
                  </div>
                )}
                <input 
                  type="file" 
                  accept="image/*" 
                  capture="environment" 
                  ref={fileInputRef}
                  onChange={handleImageUpload}
                  className="hidden" 
                />
              </div>

              {isCompressing && <p className="text-center text-blue-500 text-sm mb-4">處理照片中...</p>}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">借用人姓名</label>
                  <div className="relative">
                    <User className="absolute left-3 top-3 text-gray-400" size={18} />
                    <input
                      type="text"
                      placeholder="輸入姓名"
                      value={formData.name}
                      onChange={e => setFormData({...formData, name: e.target.value})}
                      className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="relative flex py-1 items-center">
                    <div className="flex-grow border-t border-gray-200"></div>
                    <span className="flex-shrink-0 mx-4 text-gray-400 text-xs">二擇一或全填</span>
                    <div className="flex-grow border-t border-gray-200"></div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">電話分機</label>
                  <div className="relative">
                    <Phone className="absolute left-3 top-3 text-gray-400" size={18} />
                    <input
                      type="tel"
                      placeholder="輸入分機號碼"
                      value={formData.extension}
                      onChange={e => setFormData({...formData, extension: e.target.value})}
                      className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                {error && (
                  <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm flex items-start gap-2">
                    <XCircle size={18} className="mt-0.5 flex-shrink-0" />
                    {error}
                  </div>
                )}

                {successMsg && (
                   <div className="bg-green-50 text-green-600 p-3 rounded-lg text-sm flex items-start gap-2">
                     <CheckCircle size={18} className="mt-0.5 flex-shrink-0" />
                     {successMsg}
                   </div>
                )}

                <button 
                  type="submit" 
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg shadow-md active:scale-95 transition-transform flex justify-center items-center gap-2"
                >
                  <Save size={20} /> 
                  登記借用
                </button>
              </form>
            </div>
          </div>
        )}

        {/* === 借用中列表 === */}
        {activeTab === 'active' && (
          <div className="space-y-4 animate-fade-in">
            <h2 className="text-lg font-bold text-gray-700 px-1">借用中設備 ({borrowedItems.length})</h2>
            {borrowedItems.length === 0 ? (
              <div className="text-center py-10 text-gray-400 bg-white rounded-xl shadow-sm">
                <Package size={48} className="mx-auto mb-2 opacity-30" />
                <p>目前沒有借出中的設備</p>
              </div>
            ) : (
              borrowedItems.map(item => (
                <div key={item.id} className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 flex flex-col sm:flex-row gap-4">
                  <div className="w-full sm:w-24 h-48 sm:h-24 bg-gray-100 rounded-lg overflow-hidden flex-shrink-0">
                    <img src={item.photo} alt="Device" className="w-full h-full object-cover filter grayscale" />
                  </div>
                  <div className="flex-grow flex flex-col justify-between">
                    <div>
                      <div className="text-xs text-gray-400 mb-1">{item.date}</div>
                      <div className="flex flex-wrap gap-2 text-sm text-gray-800 mb-2">
                         {item.name && <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded flex items-center gap-1"><User size={12}/> {item.name}</span>}
                         {item.extension && <span className="bg-green-50 text-green-700 px-2 py-1 rounded flex items-center gap-1"><Phone size={12}/> 分機 {item.extension}</span>}
                      </div>
                    </div>
                    <button 
                      onClick={() => openReturnModal(item.id)}
                      className="mt-2 w-full bg-orange-100 hover:bg-orange-200 text-orange-700 font-medium py-2 rounded-lg text-sm flex justify-center items-center gap-2 transition-colors active:bg-orange-300"
                    >
                      <RotateCcw size={16} /> 歸還設備
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* === 歷史紀錄列表 === */}
        {activeTab === 'history' && (
          <div className="space-y-4 animate-fade-in">
            <h2 className="text-lg font-bold text-gray-700 px-1">歷史紀錄 ({historyItems.length})</h2>
             {historyItems.length === 0 ? (
              <div className="text-center py-10 text-gray-400 bg-white rounded-xl shadow-sm">
                <History size={48} className="mx-auto mb-2 opacity-30" />
                <p>尚無歷史紀錄</p>
              </div>
            ) : (
              historyItems.map(item => (
                <div key={item.id} className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 flex gap-4 opacity-75 hover:opacity-100 transition-opacity">
                   <div className="w-16 h-16 bg-gray-100 rounded-lg overflow-hidden flex-shrink-0">
                    <img src={item.photo} alt="Device" className="w-full h-full object-cover filter grayscale" />
                  </div>
                  <div className="flex-grow">
                    <div className="flex justify-between items-start">
                        <div>
                            <div className="text-xs text-gray-500">借: {item.date}</div>
                            <div className="text-xs text-green-600 font-medium mb-1">還: {item.returnDate}</div>
                        </div>
                        <button onClick={() => openDeleteModal(item.id)} className="text-gray-300 hover:text-red-500 p-2 -mr-2 -mt-2">
                            <Trash2 size={16} />
                        </button>
                    </div>
                    <div className="text-sm font-medium text-gray-800">
                        {item.name} {item.extension ? `(分機 ${item.extension})` : ''}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </main>

      {/* 自訂確認 Modal */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 animate-fade-in">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 transform transition-all scale-100">
            <div className="flex flex-col items-center text-center">
              <div className={`p-3 rounded-full mb-4 ${confirmModal.type === 'delete' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
                {confirmModal.type === 'delete' ? <Trash2 size={32} /> : <AlertCircle size={32} />}
              </div>
              <h3 className="text-lg font-bold text-gray-800 mb-2">{confirmModal.title}</h3>
              <p className="text-gray-600 mb-6">{confirmModal.message}</p>
              <div className="flex gap-3 w-full">
                <button
                  onClick={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                  className="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={executeConfirmAction}
                  className={`flex-1 px-4 py-2 text-white rounded-lg font-medium shadow-md transition-colors ${
                    confirmModal.type === 'delete' 
                      ? 'bg-red-600 hover:bg-red-700' 
                      : 'bg-blue-600 hover:bg-blue-700'
                  }`}
                >
                  確定
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 底部導航欄 */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-6 py-2 pb-safe shadow-[0_-1px_3px_rgba(0,0,0,0.05)] flex justify-between items-center z-50">
        <TabButton 
          active={activeTab === 'borrow'} 
          onClick={() => setActiveTab('borrow')} 
          icon={<Camera size={24} />} 
          label="登記" 
        />
        <TabButton 
          active={activeTab === 'active'} 
          onClick={() => setActiveTab('active')} 
          icon={<Package size={24} />} 
          label="借用中" 
          badge={borrowedItems.length}
        />
        <TabButton 
          active={activeTab === 'history'} 
          onClick={() => setActiveTab('history')} 
          icon={<History size={24} />} 
          label="歷史" 
        />
      </nav>
      
      <style>{`
        .pb-safe {
          padding-bottom: env(safe-area-inset-bottom, 20px);
        }
        @keyframes fade-in {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
            animation: fade-in 0.2s ease-out forwards;
        }
      `}</style>
    </div>
  );
}

// 內部組件
function TabButton({ active, onClick, icon, label, badge }) {
  return (
    <button 
      onClick={onClick}
      className={`flex flex-col items-center justify-center p-2 w-16 transition-colors ${
        active ? 'text-blue-600' : 'text-gray-400 hover:text-gray-600'
      }`}
    >
      <div className="relative">
        {icon}
        {badge > 0 && (
          <span className="absolute -top-2 -right-2 bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
            {badge}
          </span>
        )}
      </div>
      <span className="text-xs mt-1 font-medium">{label}</span>
    </button>
  );
}

