import {createContext,useContext,useState,type ReactNode,type Dispatch,type SetStateAction} from 'react'
import type {State} from './types'
import {initialState} from './data'
type Store={state:State;setState:Dispatch<SetStateAction<State>>;toast:(message:string)=>void;reset:()=>void}
const Context=createContext<Store|null>(null)
export function StoreProvider({children}:{children:ReactNode}) {
 const [state,setState]=useState(initialState),[message,setMessage]=useState('')
 function toast(value:string){setMessage(value);window.setTimeout(()=>setMessage(m=>m===value?'':m),3500)}
 return <Context.Provider value={{state,setState,toast,reset:()=>{setState(initialState());toast('示例数据已重置')}}}>{children}{message&&<div className="toast" role="status">{message}</div>}</Context.Provider>
}
export function useStore(){const value=useContext(Context);if(!value)throw new Error('StoreProvider missing');return value}
