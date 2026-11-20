// Páginas das fases 5 e 6 (projectos, agentes, aprovações). Created by Redfox using Claude
import type { ComponentType } from 'react'
import Agentes from './Agentes'
import Equipa from './Equipa'
import Aprovacoes from './Aprovacoes'
import { ListaProjectos, Projecto } from './Projectos'

export const PAGINAS_EXTRA: [string, ComponentType][] = [
  ['/projectos', ListaProjectos], ['/projectos/:id', Projecto], ['/agentes', Agentes], ['/equipa', Equipa], ['/aprovacoes', Aprovacoes],
]
